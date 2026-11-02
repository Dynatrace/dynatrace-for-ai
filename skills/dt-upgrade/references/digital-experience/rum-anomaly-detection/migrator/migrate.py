"""
Entry point for the RUM alert migration.

Fetches source settings, builds the migration plan, and prints the preview.
Everything the migration acts on is held in memory — nothing is written to disk.
"""

import argparse
import sys

from actors import fetch_available_actors
from apply import (
    KIND_BOTH,
    KIND_CHOICES,
    apply_objects,
    print_results,
    print_selection,
    select_objects,
)
from client import DtClient, dtctl_available, missing_required_scopes
from dedup import apply_dedup
from fetch import (
    fetch_classic_to_frontend_id_map,
    fetch_existing_custom_alerts,
    fetch_existing_frontend_alerts,
    fetch_schemas,
    fetch_source_settings,
)
from models import SOURCE_ENV_FALLBACK, SOURCE_EXPLICIT, SOURCE_SCHEMA_DEFAULT
from report import (
    print_done,
    print_done_markdown,
    print_preview,
    print_preview_markdown,
)
from translate import build_migration_plan, build_source_data, check_kpm_coverage, schema_defaults
from validate import validate_health_objects

TIER_CHOICES = (SOURCE_EXPLICIT, SOURCE_ENV_FALLBACK, SOURCE_SCHEMA_DEFAULT)


def resolve_apps(app_filter, classic_to_frontend):
    if app_filter:
        print(f"Filtering to app: {app_filter}")
        web = [app_filter] if app_filter.startswith("APPLICATION-") else []
        mobile = [app_filter] if app_filter.startswith("MOBILE_APPLICATION-") else []
        return web, mobile

    web = [k for k in classic_to_frontend if k.startswith("APPLICATION-")]
    mobile = [k for k in classic_to_frontend if k.startswith("MOBILE_APPLICATION-")]
    print(f"  {len(web)} APPLICATION entities, {len(mobile)} MOBILE_APPLICATION entities")
    return web, mobile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("app_filter", nargs="?", default=None,
                        help="Optional app entity ID (APPLICATION-* or MOBILE_APPLICATION-*)")
    parser.add_argument("--actor", required=True, help="Actor UUID to use in created objects")
    parser.add_argument("--preview", action="store_true",
                        help="Print the migration preview and exit without writing")
    parser.add_argument("--markdown", action="store_true",
                        help="Render the preview as markdown for pasting into chat")
    parser.add_argument("--validate-only", action="store_true",
                        help="Validate the objects against the API without creating them")
    parser.add_argument("--apply", action="store_true",
                        help="Create objects on the tenant. Requires exactly one of "
                             "--apply-all, --apply-for, or --apply-tier, and a separate "
                             "confirmation from the user on top of the one for the preview.")
    parser.add_argument("--apply-all", action="store_true",
                        help="Create every object the migration generated, across every app "
                             "and every tier. A deliberate whole-tenant create, never a "
                             "default from omitting the other selectors.")
    parser.add_argument("--apply-for", metavar="APP_ID", nargs="+", default=None,
                        help="Create every object generated for these apps, whichever tier "
                             "each alert type resolved from. Accepts one or more app ids, "
                             "either classic (APPLICATION-*/MOBILE_APPLICATION-*) or "
                             "smartscape (FRONTEND-*) form.")
    parser.add_argument("--apply-tier", choices=TIER_CHOICES, default=None,
                        help="Create every object across the whole tenant that resolved from "
                             "this one tier — a bundle across apps rather than a named set.")
    parser.add_argument("--apply-kind", choices=KIND_CHOICES, default=KIND_BOTH,
                        help="Narrow the selector to health alerts only, custom metric "
                             f"alerts only, or both (default {KIND_BOTH}).")
    parser.add_argument("--apply-preview", action="store_true",
                        help="Show what the selection would create and exit. Creates nothing "
                             "and makes no create API calls.")
    args = parser.parse_args()

    if not dtctl_available():
        print("Error: an internal issue prevented this migration from running. "
              "Please try again.", file=sys.stderr)
        sys.exit(1)

    if args.apply_preview:
        args.apply = True  # same selector validation, but stops before creating

    selector_count = sum([args.apply_all, bool(args.apply_for), bool(args.apply_tier)])
    if args.apply and selector_count != 1:
        print("Error: --apply requires exactly one of --apply-all, --apply-for APP_ID..., "
              "or --apply-tier.", file=sys.stderr)
        sys.exit(1)
    bad_ids = [a for a in (args.apply_for or [])
               if not (a.startswith("APPLICATION-") or a.startswith("MOBILE_APPLICATION-")
                       or a.startswith("FRONTEND-"))]
    if bad_ids:
        print(f"Error: --apply-for takes APPLICATION-*, MOBILE_APPLICATION-*, or FRONTEND-* ids, "
              f"got {', '.join(repr(a) for a in bad_ids)}", file=sys.stderr)
        sys.exit(1)

    client = DtClient()

    missing = missing_required_scopes(client)
    if missing:
        print("Error: the active token is missing permissions required to run this "
              f"migration: {', '.join(missing)}. Ask whoever manages this environment's "
              "Dynatrace access to grant these, then try again.", file=sys.stderr)
        sys.exit(1)

    available_actors = {a["id"] for a in fetch_available_actors(client)}
    if args.actor not in available_actors:
        print(f"Error: {args.actor!r} is not one of the actors available on this environment. "
              f"Run migrator/actors.py to list them and pick one from that list — an arbitrary "
              f"actor id cannot be used.", file=sys.stderr)
        sys.exit(1)

    schemas = fetch_schemas(client)
    defaults_by_schema = {sid: schema_defaults(s) for sid, s in schemas.items()}

    unmapped = check_kpm_coverage(schemas)
    if unmapped:
        print(f"\n⚠️  Unmapped KPM value(s) in the live schemas: {', '.join(unmapped)}\n"
              f"   Response time alerts for apps using them will be skipped.\n"
              f"   Add them to KPM_TO_HEALTH_ALERT_KEY, KPM_TO_CUSTOM_ALERT_METRIC, or\n"
              f"   UNSUPPORTED_KPMS in translate.py before relying on this migration.",
              file=sys.stderr)

    raw = fetch_source_settings(client, args.app_filter)
    classic_to_frontend, frontend_names = fetch_classic_to_frontend_id_map(client)
    existing_objects = fetch_existing_frontend_alerts(client, args.app_filter, classic_to_frontend)
    # Fetched before dedup, not just before apply: the preview has to know about existing
    # custom alerts too, or it promises objects the apply step then skips.
    existing_custom = fetch_existing_custom_alerts(client)

    source = build_source_data(raw)
    all_apps, all_mobile_apps = resolve_apps(args.app_filter, classic_to_frontend)

    # Objects target the smartscape id, so an app without one cannot be migrated.
    unmapped = [a for a in all_apps + all_mobile_apps if a not in classic_to_frontend]
    if unmapped:
        print(f"\n⚠️  {len(unmapped)} app(s) have no smartscape FRONTEND id and will be skipped:",
              file=sys.stderr)
        for app_id in unmapped[:10]:
            print(f"   {app_id}", file=sys.stderr)
        if len(unmapped) > 10:
            print(f"   ... and {len(unmapped) - 10} more", file=sys.stderr)

    plan = build_migration_plan(source, all_apps, all_mobile_apps, args.actor,
                                classic_to_frontend, defaults_by_schema, args.app_filter)
    apply_dedup(plan, existing_objects, existing_custom, classic_to_frontend)

    problems = validate_health_objects(plan.health_to_create, schemas)
    if problems:
        print(f"\n⚠️  {len(problems)} generated object(s) do not match the target schema:",
              file=sys.stderr)
        for problem in problems[:20]:
            print(f"   {problem}", file=sys.stderr)
        if len(problems) > 20:
            print(f"   ... and {len(problems) - 20} more", file=sys.stderr)

    if args.preview:
        if args.markdown:
            print_preview_markdown(plan, classic_to_frontend, frontend_names, show_disclaimer=True,
                                   existing_custom_count=len(existing_custom))
        else:
            print_preview(plan, classic_to_frontend, frontend_names, show_disclaimer=True,
                          existing_custom_count=len(existing_custom))
        sys.exit(0)

    if not args.apply:
        if args.markdown:
            print_preview_markdown(plan, classic_to_frontend, frontend_names, show_disclaimer=False,
                                   existing_custom_count=len(existing_custom))
        else:
            print_preview(plan, classic_to_frontend, frontend_names, show_disclaimer=False,
                          existing_custom_count=len(existing_custom))
        if args.markdown:
            print_done_markdown(plan)
        else:
            print_done(plan)
        print("\nNot creating anything. Re-run with --apply plus --apply-all, "
              "--apply-for <APP_ID>, or --apply-tier <tier>, after a separate user "
              "confirmation, to create objects.")
        return

    # Apply / apply-preview: skip the full per-app breakdown and all disclaimers — the
    # user already saw them in the --preview step. Show only the scoped selection.
    # The confirmation table the user approves before anything is created.
    health, custom = select_objects(plan, args.apply_for, args.apply_tier, args.apply_all, args.apply_kind)
    print_selection(health, custom, markdown=args.markdown)

    if args.apply_preview:
        return

    results = apply_objects(client, plan, args.apply_for, args.apply_tier, args.apply_all, args.apply_kind,
                            existing_objects, existing_custom,
                            validate_only=args.validate_only)
    if not print_results(results, args.validate_only):
        sys.exit(1)


if __name__ == "__main__":
    main()
