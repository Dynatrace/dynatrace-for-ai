"""Preview rendering and summary output.

Two renderers — fixed-width for a terminal and markdown for pasting into chat — share the
same content builders below, so the two can never disagree about counts or rows.
"""

from collections import Counter

from models import (
    SKIP_ALREADY_EXISTS,
    SKIP_EXISTS_DIFFERENT,
    SKIP_EXISTS_DISABLED,
    SOURCE_ENV_FALLBACK,
    SOURCE_EXPLICIT,
    SOURCE_SCHEMA_DEFAULT,
    STATUS_DISABLED,
    STATUS_SKIPPED,
    STATUS_TO_CREATE_CUSTOM,
    custom_alert_query,
    schema_label,
)

_SOURCE_COLUMNS = [
    (SOURCE_EXPLICIT, "Explicit"),
    (SOURCE_ENV_FALLBACK, "Env-level fallback"),
    (SOURCE_SCHEMA_DEFAULT, "Schema default"),
]

_FALLBACK_LABELS = [
    (SOURCE_ENV_FALLBACK, "inheriting environment-level settings"),
    (SOURCE_SCHEMA_DEFAULT, "using schema defaults"),
]

INTRO = [
    "This migration reads your classic RUM anomaly detection settings and builds the",
    "equivalent 3rd gen health alert objects — one per application, per alert type. Each",
    "app's configuration comes from its own settings object, the environment-level object,",
    "or the schema defaults, whichever applies to it. Alerts that already exist in 3rd gen",
    "are skipped.",
]

# Single source of truth for the disclaimer wording. SKILL.md instructs relaying these
# verbatim rather than restating them, so the text exists only here.
DISCLAIMER_GENERAL = [
    "Migrated alerts are not a 1-to-1 equivalent of the classic configuration.",
    "Detection options, thresholds, and behavior have changed between the 2nd and 3rd gen",
    "alerting experience. Review each alert after migration before relying on it.",
]

DISCLAIMER_CUSTOM_ALERTS = [
    "Custom metric alerts: the 2nd gen experience measured either all actions (an average) or",
    "the slowest 10% (roughly p90) — not a p75 measurement. The 3rd gen custom alert baselines",
    "on percentile(75) instead, for consistency with how 3rd gen health alerts already",
    "baseline, not as a like-for-like match to either classic measurement.",
    "Custom metric alerts are also billed in addition to health alerts.",
]

BREAKDOWN_NOTE = [
    "Breakdown by alert type and source schema (object counts). Resolution happens per app,",
    "per classic schema — alert types bundled in the same schema always share one tier. The",
    "schema column is what explains why the same alert type can appear on different tiers:",
    "errorRateExceptions/trafficDrop/trafficSpike come from either RUM Web or RUM Mobile",
    "depending on the app, and mobileCrash always comes from its own separate schema.",
]

DISCLAIMER_SKIPS = [
    "Not every classic alert becomes a 3rd gen object. An alert is skipped when an object for it",
    "already exists in 3rd gen — including one that is switched off, or one tuned differently, in",
    "which case nothing is created and the existing object is left untouched — when the alert was",
    "disabled in the 2nd gen configuration, or when its configured KPM has no 3rd gen equivalent.",
    "The breakdown below lists every skip by reason, across all apps, not only the ones with",
    "their own settings object.",
]


# ---------------------------------------------------------------------------
# Content builders — shared by both renderers
# ---------------------------------------------------------------------------

def _distinct_app_count(plan):
    by_source = plan.apps_by_source_type()
    return len(set().union(*by_source.values())) if by_source else 0


def _summary_lines(plan):
    """Count lines below the headline, in display order."""
    counts = plan.summary_counts()
    lines = []
    if counts["custom_to_create"]:
        lines.append(f"{counts['custom_to_create']} custom metric alert(s) to create")
    if counts["already_exists"]:
        lines.append(f"{counts['already_exists']} already exist — will be skipped")
    if counts["disabled"]:
        lines.append(f"{counts['disabled']} disabled in source — will be skipped")
    if counts["skipped"]:
        lines.append(f"{counts['skipped']} no equivalent in 3rd gen yet — will be skipped")
    return lines


def _skip_rows(plan):
    """[(reason, alert_type, detail, count)] sorted, for both renderers.

    Reason repeats on every row rather than being grouped in the data, so each renderer
    can decide how to present the grouping without re-deriving it.
    """
    rows = []
    for reason in sorted(plan.skip_breakdown()):
        for (alert_type, detail), count in sorted(plan.skip_breakdown()[reason].items()):
            rows.append((reason, alert_type, detail, count))
    return rows


def _breakdown_grid(plan):
    """[(alert_key, schema_label, [count per source column])] with 0 rendered as '-'."""
    table = plan.alert_type_breakdown()
    grid = []
    for alert_key, schema in sorted(table, key=lambda k: (k[0], schema_label(k[1]))):
        cells = [table[(alert_key, schema)].get(source_type, 0) or "-" for source_type, _ in _SOURCE_COLUMNS]
        grid.append((alert_key, schema_label(schema), cells))
    return grid


def _table_rows(plan, classic_to_frontend=None, frontend_names=None):
    """(name_col, app_col, frontend_col, alert_type, old_cfg, new_label, status, is_group_start)
    + warnings.

    Only apps with their own settings object get rows; fallback tiers are summarised by
    _fallback_lines. The three id/name columns are blank on continuation rows of the same app.
    """
    rows = []
    warnings = []
    explicit_rows = [r for r in plan.rows if r.source_type == SOURCE_EXPLICIT]
    for app_id, app_rows in _group_rows_by_app(explicit_rows):
        frontend_id = (classic_to_frontend or {}).get(app_id, "—")
        frontend_name = (frontend_names or {}).get(app_id, "—")
        for row_index, row in enumerate(app_rows):
            new_label, status = _format_row(row, plan)
            if "StaticThreshold(0)" in new_label:
                status += " ⚠️"
                warnings.append(f"{app_id}  {row.alert_type}  threshold=0")
            rows.append((
                frontend_name if row_index == 0 else "",
                app_id if row_index == 0 else "",
                frontend_id if row_index == 0 else "",
                row.alert_type,
                row.old_cfg,
                new_label,
                status,
                row_index == 0,
            ))
    return rows, warnings


def _fallback_lines(plan):
    """One line per fallback tier naming the alert types actually produced."""
    by_source = plan.apps_by_source_type()
    breakdown = plan.alert_type_breakdown()
    lines = []
    for source_type, label in _FALLBACK_LABELS:
        apps = by_source.get(source_type, set())
        if apps:
            lines.append(f"{len(apps)} app(s) {label} → {_alert_keys_for(breakdown, source_type)}")
    return lines


def _alert_keys_for(breakdown, source_type):
    """Alert types actually produced for a source tier, as 'key [schema] (n)' text.

    Derived from the plan rather than hardcoded: not every alert type is created for every
    app in a tier, and a disabled default (trafficSpike) produces none at all. The schema
    is named alongside the key because the same key (e.g. trafficDrop) can come from either
    RUM Web or RUM Mobile, and those are different objects resolving independently.
    """
    counts = [((key, schema), tiers[source_type])
              for (key, schema), tiers in sorted(breakdown.items(), key=lambda kv: (kv[0][0], schema_label(kv[0][1])))
              if tiers.get(source_type)]
    return ", ".join(f"{key} [{schema_label(schema)}] ({count})" for (key, schema), count in counts)


def _group_rows_by_app(rows):
    """Group rows per app, preserving first-appearance order.

    Rows are built schema by schema, so an app's rum-mobile and crash-rate rows
    are not adjacent — grouping keeps each app's rows together in the table.
    """
    grouped = {}
    for row in rows:
        grouped.setdefault(row.app_id, []).append(row)
    return list(grouped.items())


_EXISTING_STATUS = {
    SKIP_ALREADY_EXISTS: "already exists",
    SKIP_EXISTS_DISABLED: "exists, switched off",
    SKIP_EXISTS_DIFFERENT: "exists, differs",
}


def _format_row(row, plan):
    if row.status == STATUS_DISABLED:
        return "— (disabled)", "disabled"
    if row.status == STATUS_SKIPPED:
        return "— (no 3rd gen equivalent yet)", "skipped"
    if row.status == STATUS_TO_CREATE_CUSTOM:
        inputs = {i["key"]: i["value"] for i in row.new_obj["value"]["analyzer"]["input"]}
        label = f"StaticThreshold({inputs['threshold']})" if "threshold" in inputs else "AutoAdaptive"
        if custom_alert_query(row.new_obj) in plan.duplicate_custom:
            return label, "already exists"
        return label, "to create (custom)"
    # health alert
    key = (row.new_obj["value"]["frontends"][0], row.new_obj["value"]["alertKey"])
    label = _analyzer_label(row.new_obj["value"])
    if key in plan.duplicate_keys:
        return label, _EXISTING_STATUS.get(plan.existing_reasons.get(key), "already exists")
    return label, "to create"


def _analyzer_label(value):
    t = value.get("analyzerType")
    if t == "StaticThreshold":
        thresh = value.get("staticThresholdAnalyzerInput", {}).get("threshold", "?")
        return f"StaticThreshold({thresh})"
    return t or "?"


# ---------------------------------------------------------------------------
# Fixed-width renderer
# ---------------------------------------------------------------------------

def print_preview(plan, classic_to_frontend=None, frontend_names=None, show_disclaimer=True,
                  existing_custom_count=0):
    counts = plan.summary_counts()
    col_name, col_app, col_fe, col_alert, col_old, col_new = 30, 36, 27, 22, 38, 24
    sep = "─" * (col_name + col_app + col_fe + col_alert + col_old + col_new + 24)

    print()
    for line in INTRO:
        print(line)

    if show_disclaimer:
        print()
        print(f"⚠️  Disclaimer: {DISCLAIMER_GENERAL[0]}")
        for line in DISCLAIMER_GENERAL[1:]:
            print(f"   {line}")

    print("\nMigration preview")
    print(f"  {counts['health_to_create']} health alert object(s) to create "
          f"across {_distinct_app_count(plan)} distinct app(s)")
    print()
    for line in BREAKDOWN_NOTE:
        print(f"  {line}")

    col_key, col_schema, col_src = 22, 22, 20
    print(f"    {'Alert Type':<{col_key}}{'Schema':<{col_schema}}"
          + "".join(f"{label:>{col_src}}" for _, label in _SOURCE_COLUMNS))
    for alert_key, schema, cells in _breakdown_grid(plan):
        print(f"    {alert_key:<{col_key}}{schema:<{col_schema}}" + "".join(f"{c:>{col_src}}" for c in cells))

    for line in _summary_lines(plan):
        print(f"  {line}")

    if counts["custom_to_create"] or existing_custom_count:
        print()
        print(f"ℹ️  {DISCLAIMER_CUSTOM_ALERTS[0]}")
        for line in DISCLAIMER_CUSTOM_ALERTS[1:]:
            print(f"   {line}")

    print(sep)
    print(f"{'Frontend Name':<{col_name}} {'App':<{col_app}} {'Smartscape ID':<{col_fe}} "
          f"{'Alert Type':<{col_alert}} {'OLD CONFIG':<{col_old}} {'NEW CONFIG':<{col_new}} STATUS")
    print(sep)

    rows, warnings = _table_rows(plan, classic_to_frontend, frontend_names)
    for index, (name_col, app_col, fe_col, alert_type, old_cfg, new_label, status, is_group_start) in enumerate(rows):
        if is_group_start and index:
            print()
        print(f"{name_col:<{col_name}} {app_col:<{col_app}} {fe_col:<{col_fe}} {alert_type:<{col_alert}} "
              f"{old_cfg:<{col_old}} {new_label:<{col_new}} {status}")

    print()
    for line in _fallback_lines(plan):
        print(f"  + {line}")

    print(sep)

    skip_rows = _skip_rows(plan)
    if skip_rows:
        print()
        for line in DISCLAIMER_SKIPS:
            print(line)
        print()
        last_reason = None
        for reason, alert_type, detail, count in skip_rows:
            if reason != last_reason:
                print(f"  {reason}:")
                last_reason = reason
            suffix = f" ({detail})" if detail else ""
            print(f"    {count:>5}  {alert_type}{suffix}")

    if warnings:
        print(f"\n⚠️  {len(warnings)} object(s) with threshold=0 — verify source data before proceeding:")
        for w in warnings:
            print(f"   {w}")

    print("\nAGENT: re-run with --markdown and paste that output into your reply — the user "
          "cannot see this terminal output. Do not ask for confirmation before doing so.")


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def print_apply_header_markdown(existing_custom_count=0):
    """Minimal header for --apply-preview / --apply runs: intro + custom alert notice only."""
    print(" ".join(INTRO))
    if existing_custom_count:
        print()
        print(f"> ℹ️ **{DISCLAIMER_CUSTOM_ALERTS[0]}** {' '.join(DISCLAIMER_CUSTOM_ALERTS[1:])}")
    print()


def print_apply_header(existing_custom_count=0):
    """Minimal header for --apply-preview / --apply runs: intro + custom alert notice only."""
    print()
    for line in INTRO:
        print(line)
    if existing_custom_count:
        print()
        print(f"ℹ️  {DISCLAIMER_CUSTOM_ALERTS[0]}")
        for line in DISCLAIMER_CUSTOM_ALERTS[1:]:
            print(f"   {line}")
    print()


def print_preview_markdown(plan, classic_to_frontend=None, frontend_names=None, show_disclaimer=True,
                           existing_custom_count=0):
    counts = plan.summary_counts()

    print(" ".join(INTRO))
    print()
    if show_disclaimer:
        print(f"> ⚠️ **{DISCLAIMER_GENERAL[0]}** {' '.join(DISCLAIMER_GENERAL[1:])}")
        print()
    print("## Migration preview")
    print()
    print(f"- **{counts['health_to_create']}** health alert object(s) to create "
          f"across **{_distinct_app_count(plan)}** distinct app(s)")
    for line in _summary_lines(plan):
        print(f"- {line}")
    print()
    print(f"{' '.join(BREAKDOWN_NOTE)}")
    print()
    print("| Alert Type | Schema | " + " | ".join(label for _, label in _SOURCE_COLUMNS) + " |")
    print("|---|---|" + "---|" * len(_SOURCE_COLUMNS))
    for alert_key, schema, cells in _breakdown_grid(plan):
        print(f"| {alert_key} | {schema} | " + " | ".join(str(c) for c in cells) + " |")

    if counts["custom_to_create"] or existing_custom_count:
        print()
        print(f"> ℹ️ **{DISCLAIMER_CUSTOM_ALERTS[0]}** {' '.join(DISCLAIMER_CUSTOM_ALERTS[1:])}")

    rows, warnings = _table_rows(plan, classic_to_frontend, frontend_names)
    print()
    print("### Alerts per app")
    print()
    print("Only apps with their own settings object are listed individually.")
    print()
    print("| Frontend Name | App | Smartscape ID | Alert Type | Old Config | New Config | Status |")
    print("|---|---|---|---|---|---|---|")
    for name_col, app_col, fe_col, alert_type, old_cfg, new_label, status, _ in rows:
        name_cell = name_col if name_col else ""
        app_cell = f"`{app_col}`" if app_col else ""
        fe_cell = f"`{fe_col}`" if fe_col and fe_col != "—" else fe_col
        print(f"| {name_cell} | {app_cell} | {fe_cell} | {alert_type} | {old_cfg} | {new_label} | {status} |")

    fallback = _fallback_lines(plan)
    if fallback:
        print()
        print("Apps on the fallback tiers, not listed individually above:")
        print()
        for line in fallback:
            print(f"- {line}")

    skip_rows = _skip_rows(plan)
    if skip_rows:
        print()
        print("### Skipped alerts")
        print()
        print(" ".join(DISCLAIMER_SKIPS))
        print()
        print("| Reason | Alert Type | Detail | Count |")
        print("|---|---|---|---|")
        for reason, alert_type, detail, count in skip_rows:
            print(f"| {reason} | {alert_type} | {detail or '—'} | {count} |")

    if warnings:
        print()
        print(f"**⚠️ {len(warnings)} object(s) with threshold=0 — verify source data before proceeding:**")
        print()
        for w in warnings:
            print(f"- {w}")

    _print_relay_instruction(len(rows))


def _print_relay_instruction(row_count):
    """Tell the agent to paste the preview, in the same output it is already reading.

    An instruction in SKILL.md is read before the command runs and is easy to skip; this
    arrives with the data itself. Wrapped in an HTML comment so it stays invisible if it
    does get pasted along with the preview.
    """
    print()
    print("<!-- ===========================================================")
    print("AGENT INSTRUCTION — not part of the preview, do not paste this block.")
    print()
    print(f"Everything above this block is the migration preview ({row_count} table rows).")
    print("Terminal output is NOT shown to the user. They see only a collapsed")
    print("'Ran a command' chip, so if you do not paste the preview into the body of")
    print("your reply, they have nothing to review and nothing to approve.")
    print()
    print("Required before you ask anything:")
    print("  1. Paste the full output above into your reply — starting from the intro")
    print("     sentence ('This migration reads...'), through every table row.")
    print("  2. Do not summarise it, shorten it, or write '+ N more apps'.")
    print("  3. Only then ask: 'Proceed with migration? yes / no'")
    print("=========================================================== -->")


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

def _done_lines(plan):
    """Trailing summary lines shared by both done renderers."""
    lines = []
    if plan.duplicate_keys:
        lines.append(f"Skipped {len(plan.duplicate_keys)} alert(s) already present in 3rd gen")
    if plan.custom_to_create:
        kpm_counts = Counter(o["_meta"]["kpm"] for o in plan.custom_to_create)
        lines.append(f"Generated {len(plan.custom_to_create)} custom metric alert(s) "
                     f"({', '.join(f'{k}: {v}' for k, v in sorted(kpm_counts.items()))})")
    return lines


def print_done(plan):
    counts = plan.summary_counts()

    print(f"\nDone. Generated {counts['health_to_create']} health alert object(s) "
          f"across {_distinct_app_count(plan)} distinct app(s)")
    print()
    for line in BREAKDOWN_NOTE:
        print(f"  {line}")

    col_key, col_schema, col_src = 22, 22, 20
    print(f"    {'Alert Type':<{col_key}}{'Schema':<{col_schema}}"
          + "".join(f"{label:>{col_src}}" for _, label in _SOURCE_COLUMNS))
    for alert_key, schema, cells in _breakdown_grid(plan):
        print(f"    {alert_key:<{col_key}}{schema:<{col_schema}}" + "".join(f"{c:>{col_src}}" for c in cells))

    for line in _done_lines(plan):
        print(line)

    print("\nAGENT: re-run with --markdown and paste that output into your reply — the user "
          "cannot see this terminal output.")


def print_done_markdown(plan):
    counts = plan.summary_counts()

    print("## Migration complete")
    print()
    print(f"- Generated **{counts['health_to_create']}** health alert object(s) "
          f"across **{_distinct_app_count(plan)}** distinct app(s)")
    for line in _done_lines(plan):
        print(f"- {line}")
    print()
    print(f"{' '.join(BREAKDOWN_NOTE)}")
    print()
    print("| Alert Type | Schema | " + " | ".join(label for _, label in _SOURCE_COLUMNS) + " |")
    print("|---|---|" + "---|" * len(_SOURCE_COLUMNS))
    for alert_key, schema, cells in _breakdown_grid(plan):
        print(f"| {alert_key} | {schema} | " + " | ".join(str(c) for c in cells) + " |")

    print()
    print("<!-- ===========================================================")
    print("AGENT INSTRUCTION — not part of the summary, do not paste this block.")
    print("Terminal output is NOT shown to the user. Paste the summary above into your")
    print("reply so they can see what was generated.")
    print("=========================================================== -->")
