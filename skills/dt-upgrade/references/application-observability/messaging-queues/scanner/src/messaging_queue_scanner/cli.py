"""Command-line entry point for the read-only messaging queue scanner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import DEFAULT_DIR_NAME, for_dtctl, for_http, resolve_output_dir
from .enrich import fetch_queues
from .report import (
    add_queue_links,
    build_summary,
    write_html,
    write_scan_data,
    write_summary,
)
from .scan import Finding, scan_item
from .shared import (
    ConfigError,
    DtctlAuthError,
    DtctlClient,
    DtctlError,
    HttpClient,
    gather_sources,
    preflight,
    add_artifact_links,
    report_ui_url,
    strip_cached_results,
)


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _announce(
    summary: dict[str, Any],
    summary_path: Path,
    html_path: Path,
    scan_data_path: Path | None = None,
    fixture: bool = False,
) -> None:
    if fixture:
        print("Rendered fixture data; no tenant was contacted.")
    totals = summary.get("totals", {})
    print(f"verdict  : {summary.get('verdict')} - {summary.get('verdict_note')}")
    print(
        f"review   : {totals.get('artifacts_affected', 0)} configuration(s), "
        f"{totals.get('references', 0)} reference(s)"
    )
    if summary.get("incomplete_sources"):
        print(f"warning  : incomplete sources - {', '.join(summary['incomplete_sources'])}")
    print(f"summary  : {summary_path}")
    print(f"report   : {html_path}")
    if scan_data_path:
        print(f"cache    : {scan_data_path}")


def cmd_scan(args: argparse.Namespace) -> int:
    if args.transport == "dtctl":
        cfg = for_dtctl(
            context=args.context,
            ui_url=args.ui_url,
            output_dir=args.output_dir,
            timestamped=args.timestamp,
            timeout=args.timeout,
            max_workers=args.max_workers,
        )
        client: Any = DtctlClient(cfg)
        _log(f"Transport : dtctl (context {cfg.dtctl_context})")
        _log(f"Tenant    : {cfg.tenant_label}")
        preflight(cfg.dtctl_context)
        _log("Auth      : ok")
    else:
        cfg = for_http(
            tenant=args.tenant,
            classic_url=args.classic_url,
            platform_url=args.platform_url,
            ui_url=args.ui_url,
            platform_token=args.platform_token,
            output_dir=args.output_dir,
            timestamped=args.timestamp,
            timeout=args.timeout,
            max_workers=args.max_workers,
        )
        client = HttpClient(cfg)
        _log("Transport : http (platform token)")
        _log(f"Tenant    : {cfg.tenant_label}")

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    _log(f"Workdir   : {cfg.output_dir}\n")
    sources = gather_sources(client, log=_log)
    findings: list[Finding] = []
    affected_configurations: list[dict[str, Any]] = []

    for source in sources:
        affected = 0
        for item in source.items:
            item_findings = scan_item(item)
            if item_findings:
                affected += 1
                findings.extend(item_findings)
                affected_configurations.append(
                    {
                        "source": item["source"],
                        "kind": item["kind"],
                        "id": item.get("id") or "",
                        "name": item.get("name") or item.get("id") or "<unnamed>",
                        "scope": item.get("scope"),
                        "body": strip_cached_results(item.get("body")),
                    }
                )
        _log(
            f"  {source.name:<14} {source.state:<9} "
            f"{source.items_checked:>5} checked, {affected:>4} to review"
        )
        source.items = []

    queue_ids = {queue_id for finding in findings for queue_id in finding.queue_ids}
    resolved_queues, queue_source = fetch_queues(client, queue_ids)
    _log(
        f"  queue lookup   {queue_source.state:<9} "
        f"{len(resolved_queues):>5}/{len(queue_ids)} resolved"
    )

    summary = build_summary(
        cfg=cfg,
        findings=findings,
        sources=sources,
        resolved_queues=resolved_queues,
    )
    summary["enrichment"] = {
        "queue_lookup": {
            "state": queue_source.state,
            "reason": queue_source.reason,
            "ids_checked": queue_source.items_checked,
            "ids_resolved": len(resolved_queues),
        }
    }
    summary_path = write_summary(cfg.output_dir, summary)
    scan_data_path = write_scan_data(cfg.output_dir, summary, affected_configurations)
    html_path = write_html(cfg.output_dir, summary)
    _announce(summary, summary_path, html_path, scan_data_path)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    output_dir = resolve_output_dir(args.output_dir)
    summary_path = output_dir / "summary.json"
    if not summary_path.is_file():
        _log(f"no summary.json in {output_dir}")
        return 1
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    ui_url = report_ui_url(summary, args.ui_url)
    summary.setdefault("tenant", {})["ui_url"] = ui_url
    add_artifact_links(summary.get("artifacts", []), ui_url)
    add_queue_links(summary.get("queues", []), ui_url)
    write_summary(output_dir, summary)
    scan_data_path = output_dir / "scan-data.json"
    if scan_data_path.is_file():
        scan_data = json.loads(scan_data_path.read_text(encoding="utf-8"))
        scan_data["tenant"] = summary.get("tenant")
        add_artifact_links(scan_data.get("artifacts", []), ui_url)
        add_queue_links(scan_data.get("queues", []), ui_url)
        write_scan_data(
            output_dir,
            scan_data,
            scan_data.get("configurations", []),
        )
    _announce(
        summary,
        summary_path,
        write_html(output_dir, summary),
        scan_data_path if scan_data_path.is_file() else None,
    )
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    fixture = Path(__file__).resolve().parent / "fixtures" / "demo_summary.json"
    summary = json.loads(fixture.read_text(encoding="utf-8"))
    output_dir = resolve_output_dir(args.output_dir)
    summary_path = write_summary(output_dir, summary)
    html_path = write_html(output_dir, summary)
    _announce(summary, summary_path, html_path, fixture=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="messaging-queue-scanner",
        description="Find configurations that reference classic queue entities or metrics.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="scan a tenant and write the report")
    scan.add_argument("--transport", choices=("dtctl", "http"), default="dtctl")
    scan.add_argument("--context", help="dtctl context (default: current context)")
    scan.add_argument("--tenant", help="[http] tenant URL")
    scan.add_argument("--classic-url", help="[http] override classic API URL")
    scan.add_argument("--platform-url", help="[http] override platform API URL")
    scan.add_argument("--ui-url", help="tenant UI URL used for configuration links")
    scan.add_argument("--platform-token", help="[http] platform token; prefer DT_PLATFORM_TOKEN")
    scan.add_argument("--output-dir", help=f"output directory (default: ./{DEFAULT_DIR_NAME}/)")
    scan.add_argument("--timestamp", action="store_true", help="keep a timestamped output directory")
    scan.add_argument("--timeout", type=int, default=60)
    scan.add_argument("--max-workers", type=int, default=10)
    scan.set_defaults(func=cmd_scan)

    render = commands.add_parser("render", help="rebuild report.html from summary.json")
    render.add_argument("--output-dir")
    render.add_argument("--ui-url", help="tenant UI URL used to add or repair configuration links")
    render.set_defaults(func=cmd_render)

    demo = commands.add_parser("demo", help="render fixture data without contacting a tenant")
    demo.add_argument("--output-dir")
    demo.set_defaults(func=cmd_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        _log(f"configuration error: {exc}")
    except DtctlAuthError as exc:
        _log(f"dtctl authentication error: {exc}")
    except DtctlError as exc:
        _log(f"dtctl error: {exc}")
    except KeyboardInterrupt:
        _log("interrupted")
    return 1
