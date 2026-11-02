"""Creates the generated objects in the tenant.

This is the only part of the skill that writes to a Dynatrace environment. It is guarded in
migrate.py behind an explicit --apply flag plus exactly one selector, so nothing is ever
created without the user having named either a specific app or a specific tier.

`_meta` is stripped here: it is traceability for the generated files and is not part of
either schema.
"""

from models import custom_alert_query, tier_label
from schema_ids import SCHEMA_CUSTOM_ALERT, SCHEMA_FRONTEND_ALERT

ALERT_TYPE_HEALTH = "Health alert"
ALERT_TYPE_CUSTOM = "Custom metric alert"

# Both schemas are created at environment scope. The custom alert schema also accepts
# "tenant", but existing objects on the tenant report "environment", so we match those.
SCOPE = "environment"


KIND_HEALTH = "health"
KIND_CUSTOM = "custom"
KIND_BOTH = "both"
KIND_CHOICES = (KIND_HEALTH, KIND_CUSTOM, KIND_BOTH)


def select_objects(plan, app_ids=None, source_type=None, apply_all=False, kind=KIND_BOTH):
    """(health, custom) objects to create. Exactly one of app_ids / source_type / apply_all.

    - app_ids: every object generated for those apps, whichever tier each alert type
      resolved from. An app's alert types resolve tiers independently (each one already
      picked its own settings object, its environment object, or the schema defaults), so
      "the settings for this app" means all of them — there is no separate tier choice for
      a single app.
    - source_type: every object across the whole tenant that resolved from that one tier
      (SOURCE_EXPLICIT / SOURCE_ENV_FALLBACK / SOURCE_SCHEMA_DEFAULT from models.py), for
      creating a bundle across many apps rather than a named set.
    - apply_all: every object the migration generated, across every app and every tier.
      Kept as its own explicit flag rather than "just omit the other two", so a whole-tenant
      create is always a deliberate choice, never an accidental default from a missing
      argument.

    `kind` narrows any of the three to health alerts only, custom metric alerts only, or
    both. It is orthogonal to the selector: a caller can ask for one app's custom alerts,
    every schema-default health alert, or all custom alerts tenant-wide.

    `_meta.appId` is the classic app id, `_meta.frontendId` the smartscape id, and
    `_meta.sourceType` the tier — all recorded by every object builder regardless of which
    tier the object came from. `app_ids` may mix classic ids (`APPLICATION-*` /
    `MOBILE_APPLICATION-*`) and smartscape ids (`FRONTEND-*`); each entry is matched against
    whichever id form it looks like it is.
    """
    selectors_given = sum([app_ids is not None, source_type is not None, bool(apply_all)])
    if selectors_given != 1:
        raise ValueError("select_objects requires exactly one of app_ids, source_type, or apply_all")
    if kind not in KIND_CHOICES:
        raise ValueError(f"kind must be one of {KIND_CHOICES}, got {kind!r}")

    if apply_all:
        matches = lambda obj: True
    elif app_ids is not None:
        wanted = set(app_ids)
        matches = lambda obj: obj["_meta"].get("appId") in wanted or obj["_meta"].get("frontendId") in wanted
    else:
        matches = lambda obj: obj["_meta"].get("sourceType") == source_type

    health = [o for o in plan.health_to_create if matches(o)] \
        if kind in (KIND_HEALTH, KIND_BOTH) else []
    custom = [o for o in plan.custom_to_create if matches(o)] \
        if kind in (KIND_CUSTOM, KIND_BOTH) else []
    return health, custom


def apply_objects(client, plan, app_ids=None, source_type=None, apply_all=False, kind=KIND_BOTH,
                  existing_objects=(), existing_custom=(), validate_only=False):
    """Create every object selected by app_ids / source_type / apply_all. Returns
    [(description, ok, message)].

    Migration dedup ignores existing objects that are disabled, on the grounds that a
    disabled alert is not really alerting. That is right for planning but wrong for
    creating: it would leave two objects for the same alert on the same frontend. So the
    apply step skips anything already present, enabled or not.
    """
    present_health = {(o.get("value", {}).get("alertKey"), frontend)
                      for o in existing_objects
                      for frontend in o.get("value", {}).get("frontends", [])}
    present_custom = {q for o in existing_custom if (q := custom_alert_query(o))}
    health_objects, custom_objects = select_objects(plan, app_ids, source_type, apply_all, kind)

    results = []
    for obj in health_objects:
        key = (obj["value"]["alertKey"], obj["value"]["frontends"][0])
        if key in present_health:
            results.append((_health_label(obj), True, "skipped — already on the tenant"))
            continue
        results.append(_create(client, SCHEMA_FRONTEND_ALERT, obj, _health_label(obj), validate_only))

    for obj in custom_objects:
        if custom_alert_query(obj) in present_custom:
            results.append((_custom_label(obj), True, "skipped — already on the tenant"))
            continue
        results.append(_create(client, SCHEMA_CUSTOM_ALERT, obj, _custom_label(obj), validate_only))
    return results


def _create(client, schema_id, obj, label, validate_only):
    ok, message = client.create_settings(schema_id, SCOPE, obj["value"], validate_only)
    return label, ok, message


def _health_label(obj):
    return f"{obj['value']['alertKey']} ({obj['value']['frontends'][0]})"


def _custom_label(obj):
    return f"custom alert: {obj['value']['title']}"


def summarise_selection(health, custom):
    """(total, distinct_apps, [(alert_type, key, scope, count)]) for the confirmation table.

    One row per distinct (alert type, key, scope) — never one per object. The shape is the
    same for a single app and for a 500-object tier bundle, so the confirmation the user
    sees does not change depending on what they selected. Counts are exact, so the totals
    always reconcile with what will actually be created.
    """
    counts = {}
    for obj in health:
        entry = (ALERT_TYPE_HEALTH, obj["value"]["alertKey"], tier_label(obj["_meta"]["sourceType"]))
        counts[entry] = counts.get(entry, 0) + 1
    for obj in custom:
        entry = (ALERT_TYPE_CUSTOM, obj["value"]["title"], tier_label(obj["_meta"]["sourceType"]))
        counts[entry] = counts.get(entry, 0) + 1

    objects = list(health) + list(custom)
    apps = {o["_meta"].get("appId") for o in objects}
    rows = [(a, k, s, c) for (a, k, s), c in sorted(counts.items())]
    return len(objects), len(apps), rows


def print_selection(health, custom, markdown=False):
    """The confirmation table. Deliberately has no analyzer type or threshold — at this
    point the user is choosing what to create, not reviewing how it is tuned."""
    total, apps, rows = summarise_selection(health, custom)

    if markdown:
        print("## Objects to create")
        print()
        print(f"**{total}** object(s) across **{apps}** app(s)")
        print()
        print("| Alert type | Key | Scope | Objects |")
        print("|---|---|---|---|")
        for alert_type, key, scope, count in rows:
            print(f"| {alert_type} | {key} | {scope} | {count} |")
        return

    col_type, col_key, col_scope = 21, 34, 19
    print(f"\n{total} object(s) across {apps} app(s) will be created:\n")
    print(f"{'Alert type':<{col_type}} {'Key':<{col_key}} {'Scope':<{col_scope}} Objects")
    for alert_type, key, scope, count in rows:
        print(f"{alert_type:<{col_type}} {key:<{col_key}} {scope:<{col_scope}} {count}")


def print_results(results, validate_only):
    """Aggregate counts for ok/skip; every failure listed individually.

    Failures are the one thing that must never be summarised away, however many there are.
    """
    verb = "validated" if validate_only else "created"
    skipped = [r for r in results if r[1] and r[2].startswith("skipped")]
    succeeded = [r for r in results if r[1] and r not in skipped]
    failed = [r for r in results if not r[1]]

    print(f"\n{len(succeeded)} of {len(results)} object(s) {verb}"
          f"{f', {len(skipped)} already on the tenant' if skipped else ''}"
          f"{f', {len(failed)} FAILED' if failed else ''}.")

    for label, _, message in failed:
        print(f"   FAIL  {label}")
        for line in message.splitlines():
            print(f"         {line}")
    return not failed
