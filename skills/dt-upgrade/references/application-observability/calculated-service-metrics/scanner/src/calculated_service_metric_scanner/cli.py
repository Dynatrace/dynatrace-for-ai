"""Command-line entry point for the calculated service metric usage scanner."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import DEFAULT_DIR_NAME, for_dtctl, for_http, resolve_output_dir
from .inventory import fetch_metric_keys
from .migration import (
    DEFAULT_WINDOW,
    PROCESSOR_DIR,
    assess,
    fetch_definitions,
    keys_with_data,
    load_default_catalog,
    totals,
    write_processors,
)
from .report import (
    add_metric_links,
    attach_migration,
    rebuild_migration_views,
    backfill_generations,
    build_summary,
    classic_base_url,
    write_html,
    write_scan_data,
    write_summary,
)
from .scan import Finding, drop_undefined_classic_keys, scan_item
from .shared import (
    COMPLETE,
    ConfigError,
    DtctlAuthError,
    DtctlClient,
    DtctlError,
    HttpClient,
    add_artifact_links,
    gather_sources,
    preflight,
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
        f"review   : {totals.get('metrics_referenced', 0)} metric(s), "
        f"{totals.get('artifacts_affected', 0)} configuration(s)"
    )
    print(
        f"split    : {totals.get('metrics_referenced_platform', 0)} metric(s) read by a "
        f"platform configuration, {totals.get('metrics_referenced_classic_only', 0)} read only "
        f"by classic ones; {totals.get('artifacts_classic', 0)} classic configuration(s)"
    )
    migration = summary.get("migration") or {}
    if migration.get("assessed"):
        counts = migration.get("totals") or {}
        print(
            f"migrate  : {counts.get('migratable_total', 0)} of {migration['assessed']} "
            f"metric(s) can be migrated "
            f"({counts.get('migratable_inexact', 0)} not exactly), "
            f"{counts.get('not_migratable', 0)} cannot, "
            f"{counts.get('no_traffic', 0)} without data in the last "
            f"{migration.get('traffic_window')}"
        )
    if summary.get("incomplete_sources"):
        print(f"warning  : incomplete sources - {', '.join(summary['incomplete_sources'])}")
    print(f"summary  : {summary_path}")
    print(f"report   : {html_path}")
    if (migration.get("totals") or {}).get("migratable_total"):
        print(f"processor: {summary_path.parent / migration['processor_dir']}/")
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
    metric_inventory, inventory_source = fetch_metric_keys(client)
    _log(
        f"  metric inventory {inventory_source.state:<9} "
        f"{len(metric_inventory):>5} service.* key(s)"
    )

    # No ``include`` filter: every source the shared layer knows is scanned, so a
    # source added there is picked up here without a change. Both SLO kinds and both classic
    # alert schemas are in scope — a classic configuration cannot read a replacement metric,
    # so it is reported as its own pile of work rather than left out.
    sources = gather_sources(client, log=_log)
    metric_keys = set(metric_inventory)
    findings: list[Finding] = []
    affected_configurations: list[dict[str, Any]] = []
    for source in sources:
        affected: set[tuple[str, str]] = set()
        for item in source.items:
            item_findings = scan_item(item, metric_keys)
            if item_findings:
                affected.add((item["kind"], item.get("id") or ""))
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
            f"{source.items_checked:>5} checked, {len(affected):>4} to review"
        )
        source.items = []

    # The migration assessment. One pass over every metric the tenant *defines*, not only the
    # referenced ones: a metric nothing references still stops receiving data, and an ad-hoc
    # query leaves no configuration behind for the scan above to find.
    migration_sources = []
    records: list[dict[str, Any]] = []
    classic_url = classic_base_url(cfg.ui_url, cfg.classic_url)
    definitions_complete = False
    if args.skip_migration:
        _log("Migration : skipped (--skip-migration)")
    else:
        definitions, definitions_source = fetch_definitions(
            client, classic_url, timeout=cfg.timeout, max_workers=cfg.max_workers
        )
        migration_sources.append(definitions_source)
        _log(
            f"  definitions    {definitions_source.state:<9} "
            f"{len(definitions):>5} definition(s) read"
        )
        traffic_keys: set[str] = set()
        traffic_known = False
        if definitions:
            traffic_keys, traffic_source = keys_with_data(client, args.traffic_window)
            migration_sources.append(traffic_source)
            traffic_known = traffic_source.state == COMPLETE
            _log(
                f"  datapoints     {traffic_source.state:<9} "
                f"{len(traffic_keys):>5} metric(s) with data in the last {args.traffic_window}"
            )
        definitions_complete = definitions_source.state == COMPLETE
        records = assess(
            definitions,
            load_default_catalog(),
            keys_with_data=traffic_keys,
            traffic_known=traffic_known,
            traffic_window=args.traffic_window,
            grail_keys=set(metric_inventory),
        )

    # With the definitions in hand, the classic spelling gets a real authority: a key nothing
    # defines is not usage of a calculated service metric, it is a reference to one that is
    # gone. Reported as its own line rather than as a metric with no definition.
    stale_findings: list[Finding] = []
    if definitions_complete and definitions:
        findings, stale_findings = drop_undefined_classic_keys(
            findings, {key.removeprefix("calc:") for key in definitions}
        )
        live = {(finding.kind, finding.artifact_id) for finding in findings}
        affected_configurations = [
            configuration
            for configuration in affected_configurations
            if (configuration["kind"], configuration["id"]) in live
        ]
        if stale_findings:
            _log(
                f"  stale refs     complete  {len(stale_findings):>5} reference(s) to metric(s) "
                "this environment does not define"
            )

    summary = build_summary(
        cfg=cfg,
        findings=findings,
        stale_findings=stale_findings,
        sources=[inventory_source, *migration_sources, *sources],
        metric_inventory=metric_inventory,
    )
    if records:
        attach_migration(
            summary,
            records,
            classic_url=classic_url,
            traffic_window=args.traffic_window,
            definitions_complete=definitions_complete,
            grail_keys=set(metric_inventory),
        )
        written = write_processors(cfg.output_dir, records)
        counts = totals(records)
        _log(
            f"  processors     written   {written:>5} of "
            f"{counts['migratable_total']} migratable metric(s)"
        )
    summary_path = write_summary(cfg.output_dir, summary)
    scan_data_path = write_scan_data(
        cfg.output_dir, summary, affected_configurations
    )
    html_path = write_html(cfg.output_dir, summary)
    _announce(summary, summary_path, html_path, scan_data_path)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    output_dir = resolve_output_dir(args.output_dir)
    summary_path = output_dir / "summary.json"
    if not summary_path.is_file():
        _log(f"no summary.json in {output_dir}")
        return 1
    summary = rebuild_migration_views(
        backfill_generations(json.loads(summary_path.read_text(encoding="utf-8")))
    )
    ui_url = report_ui_url(summary, args.ui_url)
    summary.setdefault("tenant", {})["ui_url"] = ui_url
    classic_url = classic_base_url(ui_url, summary.get("tenant", {}).get("classic_url", ""))
    for metric in summary.get("metrics", []):
        add_artifact_links(metric.get("artifacts", []), ui_url)
    add_metric_links(summary.get("metrics", []), classic_url)
    write_summary(output_dir, summary)
    scan_data_path = output_dir / "scan-data.json"
    if scan_data_path.is_file():
        scan_data = backfill_generations(json.loads(scan_data_path.read_text(encoding="utf-8")))
        scan_data["tenant"] = summary.get("tenant")
        for metric in scan_data.get("metrics", []):
            add_artifact_links(metric.get("artifacts", []), ui_url)
        add_metric_links(scan_data.get("metrics", []), classic_url)
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


#: The groups ``processors`` can be asked for, named after the report sections a reader picks
#: them from. A metric that cannot be migrated has no processor, so it is in no group.
_PROCESSOR_GROUPS = {
    "migratable": ("migratable",),
    "migratable-inexact": ("migratable_inexact",),
    "all": ("migratable", "migratable_inexact"),
}


def _records(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        metric["migration"] for metric in summary.get("metrics", []) if metric.get("migration")
    ]


def cmd_processors(args: argparse.Namespace) -> int:
    """Write or print the processors a report already stands behind.

    A scan writes every processor it can. This command is how one is taken back out — by
    group, or by name, without reading the directory — for the two cases the report itself
    keeps quiet about: a metric whose migration is not exact, and one with no recent data,
    whose processor is written but not printed on the page.

    Nothing is recomputed and no tenant is contacted: the processor is in the summary, so what
    this writes is what the report was rendered from.
    """
    output_dir = resolve_output_dir(args.output_dir)
    summary_path = output_dir / "summary.json"
    if not summary_path.is_file():
        _log(f"no summary.json in {output_dir}")
        return 1
    records = _records(json.loads(summary_path.read_text(encoding="utf-8")))
    if not records:
        _log("this report carries no migration assessment; re-run the scan without --skip-migration")
        return 1

    if args.metric:
        wanted = {name.removeprefix("calc:") for name in args.metric}
        by_key = {str(record.get("metric_key")): record for record in records}
        selected = []
        for name in sorted(wanted):
            record = by_key.get(name)
            if record is None:
                _log(f"{name}: no such calculated service metric in this report")
                return 1
            if not record.get("processor"):
                _log(f"{name}: cannot be migrated, so there is no processor to write")
                return 1
            selected.append(record)
    else:
        verdicts = _PROCESSOR_GROUPS[args.group]
        selected = [
            record
            for record in records
            if record.get("processor") and record.get("verdict") in verdicts
        ]
    if not selected:
        print("nothing to write: no metric in this report matches that group")
        return 0

    directory = output_dir / PROCESSOR_DIR
    directory.mkdir(parents=True, exist_ok=True)
    for record in selected:
        body = json.dumps(record["processor"], indent=2)
        path = directory / f"{record['target_metric_key']}.json"
        path.write_text(body + "\n", encoding="utf-8")
        marker = " (not an exact migration)" if record.get("inexact") else ""
        dormant = " (no recent data)" if record.get("traffic") == "none" else ""
        print(f"{record['metric_key']} -> {path}{marker}{dormant}")
        if args.show:
            print(body)
    print(f"{len(selected)} processor(s) in {directory}/")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    fixture = Path(__file__).resolve().parent / "fixtures" / "demo_summary.json"
    summary = json.loads(fixture.read_text(encoding="utf-8"))
    output_dir = resolve_output_dir(args.output_dir)
    summary_path = write_summary(output_dir, summary)
    html_path = write_html(output_dir, summary)
    # The fixture carries migration records, so the demo writes their processors too: the point
    # of this command is to review the complete output shape without a tenant.
    write_processors(
        output_dir,
        [
            metric["migration"]
            for metric in summary.get("metrics", [])
            if metric.get("migration")
        ],
    )
    _announce(summary, summary_path, html_path, fixture=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="calculated-service-metric-scanner",
        description="Report which configurations use calculated service metrics, and which of those metrics can be migrated.",
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
    scan.add_argument(
        "--skip-migration",
        action="store_true",
        help="report usage only; do not read the classic definitions or assess replacements",
    )
    scan.add_argument(
        "--traffic-window",
        default=DEFAULT_WINDOW,
        help=f"how far back to look for datapoints before calling a metric dormant "
        f"(default: {DEFAULT_WINDOW})",
    )
    scan.set_defaults(func=cmd_scan)

    render = commands.add_parser("render", help="rebuild report.html from summary.json")
    render.add_argument("--output-dir")
    render.add_argument("--ui-url", help="tenant UI URL used to add or repair configuration links")
    render.set_defaults(func=cmd_render)

    processors = commands.add_parser(
        "processors",
        help="write or print the replacement processors an existing report carries",
    )
    processors.add_argument("--output-dir")
    processors.add_argument(
        "--group",
        choices=sorted(_PROCESSOR_GROUPS),
        default="all",
        help="which verdict to take the processors from (default: all that can be migrated)",
    )
    processors.add_argument(
        "--metric",
        action="append",
        help="one metric key, with or without the calc: prefix; repeatable",
    )
    processors.add_argument(
        "--show", action="store_true", help="print each processor body as well as writing it"
    )
    processors.set_defaults(func=cmd_processors)

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
