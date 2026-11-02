"""Duplicate detection against the objects already present in 3rd gen.

Matching deliberately mirrors what the apply step will do: an alert is a duplicate if an
object already exists for that alertKey on that frontend — regardless of whether it is
enabled, and regardless of how it is tuned. Anything looser makes the preview promise
objects the apply step then refuses to create, which is how a user ends up being told
"3 to create" and then "0 created".

The reason is recorded separately so the preview can explain the skip rather than just
counting it.
"""

from models import (
    SKIP_ALREADY_EXISTS,
    SKIP_EXISTS_DIFFERENT,
    SKIP_EXISTS_DISABLED,
    custom_alert_query,
    tier_label,
)


def apply_dedup(plan, existing_objects, existing_custom=(), classic_to_frontend=None):
    """Mark generated objects that already exist on the tenant, with the reason why."""
    for obj in plan.health_objects:
        existing = _find_existing_health(obj, existing_objects)
        if existing is None:
            continue
        key = (obj["value"]["frontends"][0], obj["value"]["alertKey"])
        reason = _classify_health(obj, existing)
        plan.duplicate_keys.add(key)
        plan.existing_reasons[key] = reason
        plan.existing_skips.append((
            reason,
            obj["value"]["alertKey"],
            tier_label(obj["_meta"].get("sourceType")),
        ))

    for obj in plan.custom_objects:
        query = custom_alert_query(obj)
        existing = next((e for e in existing_custom if custom_alert_query(e) == query), None)
        if existing is None:
            continue
        plan.duplicate_custom.add(query)
        reason = (SKIP_ALREADY_EXISTS if existing.get("value", {}).get("enabled", True)
                  else SKIP_EXISTS_DISABLED)
        plan.existing_skips.append((reason, obj["value"]["title"], "custom metric alert"))


def _find_existing_health(new_obj, existing_objects):
    """The existing object for this alert on this frontend, or None."""
    target_ids = _target_ids(new_obj)
    alert_key = new_obj["value"].get("alertKey")
    for existing in existing_objects:
        value = existing.get("value", {})
        if value.get("alertKey") != alert_key:
            continue
        if target_ids & set(value.get("frontends", [])):
            return existing
    return None


def _classify_health(new_obj, existing_obj):
    existing_value = existing_obj.get("value", {})
    if not existing_value.get("enabled", True):
        return SKIP_EXISTS_DISABLED
    if not _same_analyzer(new_obj["value"], existing_value):
        return SKIP_EXISTS_DIFFERENT
    return SKIP_ALREADY_EXISTS


def _same_analyzer(new_value, existing_value):
    analyzer_type = new_value.get("analyzerType")
    if analyzer_type != _effective_analyzer_type(existing_value):
        return False
    input_key = _analyzer_input_key(analyzer_type)
    return not input_key or new_value.get(input_key) == existing_value.get(input_key)


def _target_ids(new_obj):
    """Both ids the alert could be recorded under in 3rd gen.

    Generated objects target the smartscape id, but existing objects were created by hand
    and use either form — on one tenant, 27 of 34 used the classic id. Matching on only
    one form would miss those and re-create alerts that already exist.
    """
    ids = {new_obj["value"]["frontends"][0]}
    classic_id = new_obj.get("_meta", {}).get("appId")
    if classic_id:
        ids.add(classic_id)
    return ids


def _effective_analyzer_type(value):
    at = value.get("analyzerType")
    if at:
        return at
    for key, name in [("seasonalBaselineAnalyzerInput", "SeasonalBaseline"),
                      ("autoAdaptiveAnalyzerInput", "AutoAdaptive"),
                      ("staticThresholdAnalyzerInput", "StaticThreshold")]:
        if key in value:
            return name
    return None


def _analyzer_input_key(analyzer_type):
    return {
        "SeasonalBaseline": "seasonalBaselineAnalyzerInput",
        "AutoAdaptive": "autoAdaptiveAnalyzerInput",
        "StaticThreshold": "staticThresholdAnalyzerInput",
    }.get(analyzer_type)
