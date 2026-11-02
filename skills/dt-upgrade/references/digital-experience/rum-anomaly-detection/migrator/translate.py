"""
Translates legacy RUM anomaly-detection settings objects to
builtin:health-experience.frontend-alert objects.

Pure transformation: takes fetched settings objects in memory and returns the
migration plan. No network calls, no reading from disk. Driven by migrate.py.

Translation rules: see references/mapping-table.md

Environment-level handling:
  3rd gen has no environment-level health alerting. For each app without an
  explicit settings object, the environment-level object (or schema defaults
  if no environment object exists) is used to generate one object per app.
"""

from models import (
    SOURCE_ENV_FALLBACK,
    SOURCE_EXPLICIT,
    SOURCE_SCHEMA_DEFAULT,
    STATUS_DISABLED,
    STATUS_SKIPPED,
    STATUS_TO_CREATE,
    STATUS_TO_CREATE_CUSTOM,
    MigrationPlan,
    PreviewRow,
    SourceData,
)
from schema_ids import (
    SCHEMA_KPM_LOAD,
    SCHEMA_KPM_XHR,
    SCHEMA_RUM_MOBILE,
    SCHEMA_RUM_MOBILE_CRASH,
    SCHEMA_RUM_WEB,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KPM_TO_HEALTH_ALERT_KEY = {
    "USER_ACTION_DURATION": "userActionDuration",
    "LARGEST_CONTENTFUL_PAINT": "webVitalsLcp",
    "CUMULATIVE_LAYOUT_SHIFT": "webVitalsCls",
    # FIRST_INPUT_DELAY: skip — FID ≠ INP, not mapped yet
    # All others: custom alert via builtin:davis.anomaly-detectors
}

# responseTime can resolve to any of these three health alert keys depending on the
# configured KPM, so a bare "Response Time" title would hide which one an object actually
# is. Short, recognisable labels — matching what the custom-alert title already does for
# its own KPMs.
HEALTH_ALERT_KEY_LABELS = {
    "userActionDuration": "User Action Duration",
    "webVitalsLcp": "LCP",
    "webVitalsCls": "CLS",
}

KPM_TO_CUSTOM_ALERT_METRIC = {
    "DOM_INTERACTIVE": "dt.frontend.web.navigation.dom_interactive",
    "FIRST_INPUT_DELAY": "dt.frontend.web.page.first_input_delay",
    "LOAD_EVENT_END": "dt.frontend.web.navigation.load_event_end",
    # The classic UI label "Time to first byte" is the RESPONSE_START enum value; there is
    # no TIME_TO_FIRST_BYTE value in either KPM schema enum.
    "RESPONSE_START": "dt.frontend.web.navigation.time_to_first_byte",
}

# KPMs with no 3rd gen metric. Listed explicitly rather than left implicit so
# check_kpm_coverage can tell "deliberately unsupported" from "nobody mapped it yet".
# RESPONSE_END is not TTFB — it is when the response completed, a different measurement,
# and no 3rd gen metric covers it.
UNSUPPORTED_KPMS = {
    "LOAD_EVENT_START",
    "RESPONSE_END",
    "SPEED_INDEX",
    "VISUALLY_COMPLETE",
}

STATIC_THRESHOLD_ANALYZER = "dt.statistics.ui.anomaly_detection.StaticThresholdAnomalyDetectionAnalyzer"
AUTO_ADAPTIVE_ANALYZER = "dt.statistics.ui.anomaly_detection.AutoAdaptiveAnomalyDetectionAnalyzer"

SEASONAL_BASELINE_DEFAULTS = {"tolerance": 4, "violatingSamples": 3, "slidingWindow": 5, "dealertingSamples": 5}

# numberOfSignalFluctuations: 1 is builtin:health-experience.frontend-alert's declared
# schema default for AutoAdaptiveAnalyzerInput, and also the minimum of its 1–10 range, so
# it is the most sensitive setting available. That default applies to health alerts only.
# builtin:davis.anomaly-detectors (custom alerts) has no such field in its schema at all —
# analyzer input there is an opaque {key, value} list Davis interprets at runtime, so there
# is no schema default to point to. Before this was sent explicitly, the Davis analyzer's
# own undocumented runtime default happened to also be 1, observed via the UI, not declared
# anywhere we can verify. Sending it explicitly here removes that reliance on an unverified
# implicit value and keeps both paths at the same number on purpose — see
# make_custom_alert_object. If Davis's real default is ever confirmed to differ, or if
# there's a recommended value for migrated alerts, only this constant needs to change.
AUTO_ADAPTIVE_DEFAULTS = {"numberOfSignalFluctuations": 1, "violatingSamples": 3, "slidingWindow": 5, "dealertingSamples": 5}
STATIC_THRESHOLD_DEFAULTS = {"violatingSamples": 3, "slidingWindow": 5, "dealertingSamples": 5}


# ---------------------------------------------------------------------------
# Schema defaults
# ---------------------------------------------------------------------------

def check_kpm_coverage(schemas):
    """KPM enum values that are neither mapped nor listed as unsupported.

    Without this, a KPM value added to the schema upstream would quietly fall through to
    "no 3rd gen equivalent" and its response time alerts would be dropped with no signal.
    """
    known = set(KPM_TO_HEALTH_ALERT_KEY) | set(KPM_TO_CUSTOM_ALERT_METRIC) | UNSUPPORTED_KPMS
    declared = set()
    for schema_id in (SCHEMA_KPM_LOAD, SCHEMA_KPM_XHR):
        for enum in schemas.get(schema_id, {}).get("enums", {}).values():
            declared.update(item["value"] for item in enum.get("items", []))
    return sorted(declared - known)


def schema_defaults(schema):
    """Resolve a Settings 2.0 schema's default values into a nested dict."""
    return {name: _property_default(prop, schema, set())
            for name, prop in schema.get("properties", {}).items()}


def _property_default(prop, schema, seen):
    ref = prop.get("type")
    if isinstance(ref, dict) and "$ref" in ref:
        section, name = ref["$ref"].split("/")[1:3]
        if section == "types" and name not in seen:
            target = schema.get(section, {}).get(name, {})
            return {n: _property_default(p, schema, seen | {name})
                    for n, p in target.get("properties", {}).items()}
    return _normalize_number(prop.get("default"))


def _normalize_number(value):
    """Schemas express whole numbers as floats; keep them ints so display strings match."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# ---------------------------------------------------------------------------
# Analyzer builders
# ---------------------------------------------------------------------------

def seasonal_baseline():
    return {"analyzerType": "SeasonalBaseline", "seasonalBaselineAnalyzerInput": dict(SEASONAL_BASELINE_DEFAULTS)}


def auto_adaptive():
    return {"analyzerType": "AutoAdaptive", "autoAdaptiveAnalyzerInput": dict(AUTO_ADAPTIVE_DEFAULTS)}


def static_threshold(threshold):
    return {"analyzerType": "StaticThreshold", "staticThresholdAnalyzerInput": {"threshold": threshold, **STATIC_THRESHOLD_DEFAULTS}}


# ---------------------------------------------------------------------------
# Object builders
# ---------------------------------------------------------------------------

def make_health_object(source_obj, app_id, frontend_id, alert_key, analyzer, title_suffix, actor,
                       source_type=SOURCE_EXPLICIT):
    """Build a health alert object targeting the smartscape FRONTEND id.

    The classic app id is kept in `_meta.appId` for traceability only — `_meta` is stripped
    before the object is created, so nothing sent to the API references a classic entity.
    `_meta.frontendId` lets scope selection match on either id form.
    """
    return {
        "_meta": {
            "sourceObjectId": source_obj.get("objectId"),
            "sourceScope": source_obj.get("scope"),
            "sourceSchema": source_obj.get("schemaId"),
            "sourceType": source_type,
            "appId": app_id,
            "frontendId": frontend_id,
        },
        "schemaId": "builtin:health-experience.frontend-alert",
        "value": {
            "alertKey": alert_key,
            "enabled": True,
            "frontends": [frontend_id],
            "actor": actor,
            "title": title_suffix,
            **analyzer,
        },
    }


def make_custom_alert_object(source_obj, app_id, frontend_id, kpm, metric, mode, threshold_ms, title, actor, source_type=SOURCE_EXPLICIT):
    # p75, not a classic value — classic measured all actions (avg) or the slowest 10%
    # (~p90), never p75. Chosen for consistency with how 3rd gen health alerts baseline.
    query = (
        f"timeseries percentile({metric}, 75),\n"
        f'filter: {{ in(dt.smartscape_source.id, toSmartscapeId("{frontend_id}")) AND dt.rum.user_type == "real_user" }},\n'
        f"by: {{ dt.smartscape_source.id }},\n"
        f"interval: 1m"
    )
    if mode == "fixed":
        analyzer_name = STATIC_THRESHOLD_ANALYZER
        inputs = [
            {"key": "query.expression", "value": query},
            {"key": "threshold", "value": str(threshold_ms)},
            {"key": "alertCondition", "value": "ABOVE"},
            {"key": "alertOnMissingData", "value": "false"},
            {"key": "violatingSamples", "value": "3"},
            {"key": "slidingWindow", "value": "5"},
            {"key": "dealertingSamples", "value": "5"},
        ]
    else:
        analyzer_name = AUTO_ADAPTIVE_ANALYZER
        # numberOfSignalFluctuations is sent explicitly rather than left to the analyzer's
        # own default, so health and custom alerts provably use the same value.
        inputs = [
            {"key": "query.expression", "value": query},
            {"key": "numberOfSignalFluctuations",
             "value": str(AUTO_ADAPTIVE_DEFAULTS["numberOfSignalFluctuations"])},
            {"key": "alertOnMissingData", "value": "false"},
            {"key": "violatingSamples", "value": "3"},
            {"key": "slidingWindow", "value": "5"},
            {"key": "dealertingSamples", "value": "5"},
        ]
    return {
        "_meta": {
            "sourceObjectId": source_obj.get("objectId"),
            "sourceScope": source_obj.get("scope"),
            "sourceSchema": source_obj.get("schemaId"),
            "sourceType": source_type,
            "kpm": kpm,
            "appId": app_id,
            "frontendId": frontend_id,
        },
        "schemaId": "builtin:davis.anomaly-detectors",
        "scope": "tenant",
        "value": {
            "enabled": True,
            "title": title,
            "description": "",
            "executionSettings": {"actor": actor},
            "analyzer": {"name": analyzer_name, "input": inputs},
            "eventTemplate": {
                "properties": [
                    {"key": "dt.source_entity", "value": "{dt.source_entity}"},
                    {"key": "event.type", "value": "CUSTOM_ALERT"},
                    {"key": "event.name", "value": title},
                ]
            },
            "source": "Alert management",
        },
    }


# ---------------------------------------------------------------------------
# Translation — each function returns list[PreviewRow] (display + output unified)
# ---------------------------------------------------------------------------

def translate_rum_web(value, source_obj, app_id, actor, frontend_id, source_type=SOURCE_EXPLICIT, load_kpm=None, xhr_kpm=None):
    rows = []
    rows += _translate_web_error_rate(value.get("errorRate", {}), source_obj, app_id, frontend_id, actor, source_type)
    rows += _translate_web_traffic_drop(value.get("trafficDrops", {}), source_obj, app_id, frontend_id, actor, source_type)
    rows += _translate_web_traffic_spike(value.get("trafficSpikes", {}), source_obj, app_id, frontend_id, actor, source_type)
    rows += _translate_web_response_time(value.get("responseTime", {}), source_obj, app_id, actor, frontend_id, source_type, load_kpm, xhr_kpm)
    return rows


def _translate_web_error_rate(er, source_obj, app_id, frontend_id, actor, source_type):
    if not er:
        return []
    mode = er.get("errorRateDetectionMode", "auto")
    enabled = er.get("enabled", True)
    thresh_str = f", threshold={(er.get('errorRateFixed') or {}).get('maxFailureRateIncrease', '?')}" if mode == "fixed" else ""
    old_cfg = f"mode={mode}, enabled={enabled}{thresh_str}"
    if not enabled:
        return [PreviewRow(app_id, "errorRateExceptions", old_cfg, None, STATUS_DISABLED, source_type=source_type, schema=source_obj.get("schemaId"))]
    analyzer = seasonal_baseline() if mode == "auto" else static_threshold(
        (er.get("errorRateFixed") or {}).get("maxFailureRateIncrease", 0)
    )
    return [PreviewRow(app_id, "errorRateExceptions", old_cfg,
        make_health_object(source_obj, app_id, frontend_id, "errorRateExceptions", analyzer, "JS Error Rate", actor, source_type),
        STATUS_TO_CREATE, source_type=source_type, schema=source_obj.get("schemaId"))]


def _translate_web_traffic_drop(td, source_obj, app_id, frontend_id, actor, source_type):
    if not td:
        return []
    pct = (td.get("trafficDrops") or {}).get("trafficDropPercentage", "?")
    old_cfg = f"enabled={td.get('enabled', True)}, drop={pct}%"
    if not td.get("enabled", True):
        return [PreviewRow(app_id, "trafficDrop", old_cfg, None, STATUS_DISABLED, source_type=source_type, schema=source_obj.get("schemaId"))]
    return [PreviewRow(app_id, "trafficDrop", old_cfg,
        make_health_object(source_obj, app_id, frontend_id, "trafficDrop", seasonal_baseline(), "Traffic Drop", actor, source_type),
        STATUS_TO_CREATE, source_type=source_type, schema=source_obj.get("schemaId"))]


def _translate_web_traffic_spike(ts, source_obj, app_id, frontend_id, actor, source_type):
    if not ts:
        return []
    pct = (ts.get("trafficSpikes") or {}).get("trafficSpikePercentage", "?")
    old_cfg = f"enabled={ts.get('enabled', False)}, spike={pct}%"
    if not ts.get("enabled", False):
        return [PreviewRow(app_id, "trafficSpike", old_cfg, None, STATUS_DISABLED, source_type=source_type, schema=source_obj.get("schemaId"))]
    return [PreviewRow(app_id, "trafficSpike", old_cfg,
        make_health_object(source_obj, app_id, frontend_id, "trafficSpike", seasonal_baseline(), "Traffic Spike", actor, source_type),
        STATUS_TO_CREATE, source_type=source_type, schema=source_obj.get("schemaId"))]


def _translate_web_response_time(rt, source_obj, app_id, actor, frontend_id, source_type, load_kpm, xhr_kpm):
    if not rt:
        return []

    mode = rt.get("detectionMode", "auto")
    enabled = rt.get("enabled", True)
    threshold_ms = 0

    if mode == "auto":
        rt_auto = rt.get("responseTimeAuto", {})
        rt_all = rt_auto.get("responseTimeAll", {})
        rt_slow = rt_auto.get("responseTimeSlowest", {})
        all_str = f"+{rt_all.get('degradationMilliseconds','?')}ms/+{rt_all.get('degradationPercent','?')}%" if rt_all else ""
        slow_str = f"+{rt_slow.get('slowestDegradationMilliseconds','?')}ms/+{rt_slow.get('slowestDegradationPercent','?')}%" if rt_slow else ""
        detail = f", all={all_str}, slowest={slow_str}" if all_str or slow_str else ""
        analyzer = auto_adaptive()
    else:
        rt_fixed = rt.get("responseTimeFixed", {})
        threshold_ms = (rt_fixed.get("responseTimeAll") or {}).get("degradationMilliseconds", 0)
        slow_ms = (rt_fixed.get("responseTimeSlowest") or {}).get("slowestDegradationMilliseconds", "?")
        sens = rt_fixed.get("sensitivity", "?")
        detail = f", all={threshold_ms}ms, slowest={slow_ms}ms, sensitivity={sens}"
        analyzer = static_threshold(threshold_ms)

    if not enabled:
        return [PreviewRow(app_id, "responseTime",
            f"mode={mode}, enabled=False, load actions={load_kpm}, xhr actions={xhr_kpm}",
            None, STATUS_DISABLED, source_type=source_type, schema=source_obj.get("schemaId"))]

    rows = []
    seen_health_keys = set()
    seen_custom_kpms = set()
    for action_label, kpm in [("load actions", load_kpm), ("xhr actions", xhr_kpm)]:
        if not kpm:
            continue
        old_cfg = f"mode={mode}, enabled={enabled}, {action_label}={kpm}{detail}"
        health_key = KPM_TO_HEALTH_ALERT_KEY.get(kpm)
        if health_key:
            if health_key not in seen_health_keys:
                seen_health_keys.add(health_key)
                title = f"Response Time - {HEALTH_ALERT_KEY_LABELS[health_key]}"
                rows.append(PreviewRow(app_id, health_key, old_cfg,
                    make_health_object(source_obj, app_id, frontend_id, health_key, analyzer, title, actor, source_type),
                    STATUS_TO_CREATE, source_type=source_type, schema=source_obj.get("schemaId")))
        elif kpm not in seen_custom_kpms:
            seen_custom_kpms.add(kpm)
            metric = KPM_TO_CUSTOM_ALERT_METRIC.get(kpm)
            if metric:
                title = f"Response Time – {kpm.replace('_', ' ').title()}"
                rows.append(PreviewRow(app_id, "responseTime", old_cfg,
                    make_custom_alert_object(source_obj, app_id, frontend_id, kpm, metric, mode, threshold_ms, title, actor, source_type),
                    STATUS_TO_CREATE_CUSTOM, kpm=kpm, source_type=source_type, schema=source_obj.get("schemaId")))
            else:
                rows.append(PreviewRow(app_id, "responseTime", old_cfg, None, STATUS_SKIPPED, kpm=kpm, source_type=source_type, schema=source_obj.get("schemaId")))
    return rows


def translate_rum_mobile(value, source_obj, app_id, frontend_id, actor, source_type=SOURCE_EXPLICIT):
    rows = []
    rows += _translate_mobile_error_rate(value.get("errorRateIncrease", {}), source_obj, app_id, frontend_id, actor, source_type)
    rows += _translate_mobile_slow_user_actions(value.get("slowUserActions", {}), source_obj, app_id, frontend_id, actor, source_type)
    rows += _translate_mobile_low_load(value.get("unexpectedLowLoad", {}), source_obj, app_id, frontend_id, actor, source_type)
    rows += _translate_mobile_high_load(value.get("unexpectedHighLoad", {}), source_obj, app_id, frontend_id, actor, source_type)
    return rows


def _translate_mobile_error_rate(er, source_obj, app_id, frontend_id, actor, source_type):
    if not er:
        return []
    mode = er.get("detectionMode", "auto")
    enabled = er.get("enabled", True)
    thresh_str = f", threshold={(er.get('errorRateIncreaseFixed') or {}).get('thresholdAbsolute', '?')}" if mode == "fixed" else ""
    old_cfg = f"mode={mode}, enabled={enabled}{thresh_str}"
    if not enabled:
        return [PreviewRow(app_id, "errorRateExceptions", old_cfg, None, STATUS_DISABLED, source_type=source_type, schema=source_obj.get("schemaId"))]
    analyzer = seasonal_baseline() if mode == "auto" else static_threshold(
        (er.get("errorRateIncreaseFixed") or {}).get("thresholdAbsolute", 5)
    )
    return [PreviewRow(app_id, "errorRateExceptions", old_cfg,
        make_health_object(source_obj, app_id, frontend_id, "errorRateExceptions", analyzer, "Error Rate", actor, source_type),
        STATUS_TO_CREATE, source_type=source_type, schema=source_obj.get("schemaId"))]


def _translate_mobile_slow_user_actions(su, source_obj, app_id, frontend_id, actor, source_type):
    if not su:
        return []
    mode = su.get("detectionMode", "auto")
    enabled = su.get("enabled", True)
    thresh_str = ""
    if mode == "fixed":
        thresh = (su.get("slowUserActionsFixed") or {}).get("durationThresholdAllFixed", {}).get("durationThreshold", "?")
        thresh_str = f", threshold={thresh}ms"
    old_cfg = f"mode={mode}, enabled={enabled}{thresh_str}"
    if not enabled:
        return [PreviewRow(app_id, "userActionDuration", old_cfg, None, STATUS_DISABLED, source_type=source_type, schema=source_obj.get("schemaId"))]
    analyzer = auto_adaptive() if mode == "auto" else static_threshold(
        (su.get("slowUserActionsFixed") or {}).get("durationThresholdAllFixed", {}).get("durationThreshold", 0)
    )
    return [PreviewRow(app_id, "userActionDuration", old_cfg,
        make_health_object(source_obj, app_id, frontend_id, "userActionDuration", analyzer, "Slow User Actions", actor, source_type),
        STATUS_TO_CREATE, source_type=source_type, schema=source_obj.get("schemaId"))]


def _translate_mobile_low_load(ll, source_obj, app_id, frontend_id, actor, source_type):
    if not ll:
        return []
    old_cfg = f"enabled={ll.get('enabled', True)}, drop={ll.get('thresholdPercentage', '?')}%"
    if not ll.get("enabled", True):
        return [PreviewRow(app_id, "trafficDrop", old_cfg, None, STATUS_DISABLED, source_type=source_type, schema=source_obj.get("schemaId"))]
    return [PreviewRow(app_id, "trafficDrop", old_cfg,
        make_health_object(source_obj, app_id, frontend_id, "trafficDrop", seasonal_baseline(), "Low Load", actor, source_type),
        STATUS_TO_CREATE, source_type=source_type, schema=source_obj.get("schemaId"))]


def _translate_mobile_high_load(hl, source_obj, app_id, frontend_id, actor, source_type):
    if not hl:
        return []
    old_cfg = f"enabled={hl.get('enabled', False)}, spike={hl.get('thresholdPercentage', '?')}%"
    if not hl.get("enabled", False):
        return [PreviewRow(app_id, "trafficSpike", old_cfg, None, STATUS_DISABLED, source_type=source_type, schema=source_obj.get("schemaId"))]
    return [PreviewRow(app_id, "trafficSpike", old_cfg,
        make_health_object(source_obj, app_id, frontend_id, "trafficSpike", seasonal_baseline(), "High Load", actor, source_type),
        STATUS_TO_CREATE, source_type=source_type, schema=source_obj.get("schemaId"))]


def translate_rum_mobile_crash_rate(value, source_obj, app_id, frontend_id, actor, source_type=SOURCE_EXPLICIT):
    rows = []
    cr = value.get("crashRateIncrease", {})
    if cr:
        mode = cr.get("detectionMode", "auto")
        enabled = cr.get("enabled", True)
        # The fixed threshold field is absoluteCrashRate, not threshold — reading the wrong
        # name silently produced StaticThreshold(0), which alerts on any crash at all.
        fixed_rate = (cr.get("crashRateIncreaseFixed") or {}).get("absoluteCrashRate", 0)
        thresh_str = f", threshold={fixed_rate}%" if mode == "fixed" else ""
        old_cfg = f"mode={mode}, enabled={enabled}{thresh_str}"
        if enabled:
            analyzer = seasonal_baseline() if mode == "auto" else static_threshold(fixed_rate)
            rows.append(PreviewRow(app_id, "mobileCrash", old_cfg,
                make_health_object(source_obj, app_id, frontend_id, "mobileCrash", analyzer, "Crash Rate", actor, source_type),
                STATUS_TO_CREATE, source_type=source_type, schema=source_obj.get("schemaId")))
        else:
            rows.append(PreviewRow(app_id, "mobileCrash", old_cfg, None, STATUS_DISABLED, source_type=source_type, schema=source_obj.get("schemaId")))
    return rows


# ---------------------------------------------------------------------------
# Source data: load from disk
# ---------------------------------------------------------------------------

def _split_by_scope(items):
    by_app = {o["scope"]: o for o in items if o.get("scope") != "environment"}
    env_obj = next((o for o in items if o.get("scope") == "environment"), None)
    return by_app, env_obj


def build_source_data(raw):
    """Build SourceData from fetched settings objects keyed by schema id.

    `raw` only contains the schemas that apply to the current filter, so no
    web/mobile gating is needed here.
    """
    web_by_app, web_env_obj = _split_by_scope(raw.get(SCHEMA_RUM_WEB, []))
    mobile_by_app, mobile_env_obj = _split_by_scope(raw.get(SCHEMA_RUM_MOBILE, []))
    crash_by_app, crash_env_obj = _split_by_scope(raw.get(SCHEMA_RUM_MOBILE_CRASH, []))

    return SourceData(
        web_by_app, web_env_obj,
        mobile_by_app, mobile_env_obj,
        crash_by_app, crash_env_obj,
        _kpm_by_app(raw.get(SCHEMA_KPM_LOAD, [])),
        _kpm_by_app(raw.get(SCHEMA_KPM_XHR, [])),
    )


def _kpm_by_app(items):
    return {o["scope"]: o["value"].get("kpm")
            for o in items if o.get("scope") and o["scope"] != "environment"}


# ---------------------------------------------------------------------------
# Migration plan assembly
# ---------------------------------------------------------------------------

def build_migration_plan(source, all_apps, all_mobile_apps, actor, classic_to_frontend,
                         defaults_by_schema, app_filter=None):
    rows = []

    # KPMs are configured per application, so an app on any tier can still have its own.
    # An app with no KPM object of its own runs on the schema default, exactly as 2nd gen does.
    default_load_kpm = defaults_by_schema.get(SCHEMA_KPM_LOAD, {}).get("kpm")
    default_xhr_kpm = defaults_by_schema.get(SCHEMA_KPM_XHR, {}).get("kpm")

    def frontend_of(app_id):
        """Smartscape id for an app, or None when it has no FRONTEND node.

        Objects always target the smartscape id, so an app without one is skipped rather
        than falling back to the classic id and producing a mixed-format output.
        """
        return classic_to_frontend.get(app_id)

    def wanted(app_id, explicit_map):
        return app_id not in explicit_map and (not app_filter or app_id == app_filter)

    # rum-web: explicit app-scoped objects
    for app_id, obj in source.web_by_app.items():
        frontend_id = frontend_of(app_id)
        if (app_filter and app_id != app_filter) or not frontend_id:
            continue
        rows += translate_rum_web(
            obj["value"], obj, app_id, actor,
            frontend_id=frontend_id,
            source_type=SOURCE_EXPLICIT,
            load_kpm=source.load_kpm_by_app.get(app_id, default_load_kpm),
            xhr_kpm=source.xhr_kpm_by_app.get(app_id, default_xhr_kpm),
        )

    # rum-web: apps without explicit objects → env-level object or schema defaults
    web_fallback = source.web_env_obj or _env_fallback(
        SCHEMA_RUM_WEB, defaults_by_schema[SCHEMA_RUM_WEB])
    web_source_type = SOURCE_ENV_FALLBACK if source.web_env_obj else SOURCE_SCHEMA_DEFAULT
    non_explicit_web = [a for a in all_apps if wanted(a, source.web_by_app) and frontend_of(a)]
    web_value = web_fallback["value"]
    rt_cfg = web_value.get("responseTime", {})

    for app_id in non_explicit_web:
        frontend_id = frontend_of(app_id)
        rows += (
            _translate_web_error_rate(web_value.get("errorRate", {}), web_fallback, app_id, frontend_id, actor, web_source_type)
            + _translate_web_traffic_drop(web_value.get("trafficDrops", {}), web_fallback, app_id, frontend_id, actor, web_source_type)
            + _translate_web_traffic_spike(web_value.get("trafficSpikes", {}), web_fallback, app_id, frontend_id, actor, web_source_type))

        # The alert config comes from the fallback template, but the KPM is still the
        # app's own, falling back to the schema default when it has none.
        rows += _translate_web_response_time(
            rt_cfg, web_fallback, app_id, actor, frontend_id, web_source_type,
            source.load_kpm_by_app.get(app_id, default_load_kpm),
            source.xhr_kpm_by_app.get(app_id, default_xhr_kpm),
        )

    # rum-mobile: explicit + env/schema fallback
    if not app_filter or app_filter.startswith("MOBILE_APPLICATION-"):
        for app_id, obj in source.mobile_by_app.items():
            frontend_id = frontend_of(app_id)
            if (app_filter and app_id != app_filter) or not frontend_id:
                continue
            rows += translate_rum_mobile(obj["value"], obj, app_id, frontend_id, actor,
                                         source_type=SOURCE_EXPLICIT)

        mob_fallback = source.mobile_env_obj or _env_fallback(
            SCHEMA_RUM_MOBILE, defaults_by_schema[SCHEMA_RUM_MOBILE])
        mob_source_type = SOURCE_ENV_FALLBACK if source.mobile_env_obj else SOURCE_SCHEMA_DEFAULT

        crash_fallback = source.crash_env_obj or _env_fallback(
            SCHEMA_RUM_MOBILE_CRASH, defaults_by_schema[SCHEMA_RUM_MOBILE_CRASH])
        crash_source_type = SOURCE_ENV_FALLBACK if source.crash_env_obj else SOURCE_SCHEMA_DEFAULT

        # explicit crash-rate objects
        for app_id, obj in source.crash_by_app.items():
            frontend_id = frontend_of(app_id)
            if (app_filter and app_id != app_filter) or not frontend_id:
                continue
            rows += translate_rum_mobile_crash_rate(obj["value"], obj, app_id, frontend_id, actor,
                                                    source_type=SOURCE_EXPLICIT)

        for app_id in [a for a in all_mobile_apps if wanted(a, source.mobile_by_app) and frontend_of(a)]:
            rows += translate_rum_mobile(
                mob_fallback["value"], mob_fallback, app_id, frontend_of(app_id), actor,
                source_type=mob_source_type)

        for app_id in [a for a in all_mobile_apps if wanted(a, source.crash_by_app) and frontend_of(a)]:
            rows += translate_rum_mobile_crash_rate(
                crash_fallback["value"], crash_fallback, app_id, frontend_of(app_id), actor,
                source_type=crash_source_type)

    return MigrationPlan(rows=rows)


def _env_fallback(schema_id, defaults):
    return {"objectId": None, "scope": "environment", "schemaId": schema_id, "value": defaults}

