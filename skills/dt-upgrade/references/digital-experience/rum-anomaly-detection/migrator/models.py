"""Status/source-type constants and the data structures shared by the migration layers."""

from dataclasses import dataclass, field
from typing import Optional

from schema_ids import (
    SCHEMA_RUM_MOBILE,
    SCHEMA_RUM_MOBILE_CRASH,
    SCHEMA_RUM_WEB,
)

STATUS_TO_CREATE = "to_create"
STATUS_TO_CREATE_CUSTOM = "to_create_custom"
STATUS_DISABLED = "disabled"
STATUS_SKIPPED = "skipped"

SOURCE_EXPLICIT = "explicit"
SOURCE_ENV_FALLBACK = "environment-fallback"
SOURCE_SCHEMA_DEFAULT = "schema-default"

# Why an alert produces no 3rd gen object. Every skip falls into exactly one of these.
SKIP_ALREADY_EXISTS = "Already present in 3rd gen"
SKIP_EXISTS_DISABLED = "Already present in 3rd gen but switched off — enable it there"
SKIP_EXISTS_DIFFERENT = "Already present in 3rd gen with different settings"
SKIP_DISABLED_AT_SOURCE = "Disabled in the 2nd gen configuration"
SKIP_NO_EQUIVALENT = "No 3rd gen equivalent for the configured KPM"


def custom_alert_query(obj):
    """The analyzer's DQL, which identifies a custom alert: same metric, same frontend.

    Custom alerts have no alertKey to match on, so the query is their identity.
    """
    for entry in obj.get("value", {}).get("analyzer", {}).get("input", []):
        if entry.get("key") == "query.expression":
            return entry.get("value")
    return None


# Client-facing wording for the tiers. The internal values are jargon and must never be
# shown to the user; anything user-visible goes through here.
TIER_LABELS = {
    SOURCE_EXPLICIT: "Its own settings",
    SOURCE_ENV_FALLBACK: "Environment-level",
    SOURCE_SCHEMA_DEFAULT: "Schema default",
}


def tier_label(source_type):
    return TIER_LABELS.get(source_type, source_type)


# Same idea as TIER_LABELS, for the classic schema a row's config was read from. Several
# alert type keys (errorRateExceptions, trafficDrop, trafficSpike) are produced by both
# rum-web and rum-mobile, and each app only ever has one of the two, so the schema is what
# actually explains why the same alert type can land on a different tier for different apps.
SCHEMA_LABELS = {
    SCHEMA_RUM_WEB: "RUM Web",
    SCHEMA_RUM_MOBILE: "RUM Mobile",
    SCHEMA_RUM_MOBILE_CRASH: "RUM Mobile Crash Rate",
}


def schema_label(schema_id):
    return SCHEMA_LABELS.get(schema_id, schema_id)


@dataclass
class PreviewRow:
    app_id: str
    alert_type: str
    old_cfg: str
    new_obj: Optional[dict]
    status: str          # STATUS_TO_CREATE | STATUS_TO_CREATE_CUSTOM | STATUS_DISABLED | STATUS_SKIPPED
    kpm: Optional[str] = None
    source_type: str = SOURCE_EXPLICIT  # SOURCE_EXPLICIT | SOURCE_ENV_FALLBACK | SOURCE_SCHEMA_DEFAULT
    schema: Optional[str] = None  # the classic settings schema this row's config was read from


@dataclass
class SourceData:
    web_by_app: dict
    web_env_obj: Optional[dict]
    mobile_by_app: dict
    mobile_env_obj: Optional[dict]
    crash_by_app: dict
    crash_env_obj: Optional[dict]
    load_kpm_by_app: dict
    xhr_kpm_by_app: dict


@dataclass
class MigrationPlan:
    rows: list = field(default_factory=list)
    duplicate_keys: set = field(default_factory=set)
    duplicate_custom: set = field(default_factory=set)
    # [(reason, key_label, detail)] for everything already on the tenant, so the preview can
    # say *why* it is skipping rather than only that it is.
    existing_skips: list = field(default_factory=list)
    # (frontend_id, alertKey) -> reason, for per-row status in the preview table.
    existing_reasons: dict = field(default_factory=dict)

    @property
    def health_objects(self):
        return [r.new_obj for r in self.rows if r.status == STATUS_TO_CREATE]

    @property
    def custom_objects(self):
        return [r.new_obj for r in self.rows if r.status == STATUS_TO_CREATE_CUSTOM]

    @property
    def health_to_create(self):
        return [o for o in self.health_objects
                if (o["value"]["frontends"][0], o["value"]["alertKey"]) not in self.duplicate_keys]

    @property
    def custom_to_create(self):
        return [o for o in self.custom_objects
                if custom_alert_query(o) not in self.duplicate_custom]

    def summary_counts(self):
        return {
            "health_to_create": len(self.health_to_create),
            "custom_to_create": len(self.custom_to_create),
            "already_exists": len(self.duplicate_keys) + len(self.duplicate_custom),
            "disabled": sum(1 for r in self.rows if r.status == STATUS_DISABLED),
            "skipped": sum(1 for r in self.rows if r.status == STATUS_SKIPPED),
        }

    def apps_by_source_type(self):
        """Return {source_type: set of app_ids} over every app that gets a health alert."""
        result = {}
        for r in self.rows:
            if r.new_obj and r.status == STATUS_TO_CREATE:
                result.setdefault(r.new_obj["_meta"]["sourceType"], set()).add(
                    r.new_obj["value"]["frontends"][0])
        return result

    def skip_breakdown(self):
        """Return {reason: {(alert_type, detail): count}} over every skipped alert.

        Covers all tiers, not just apps with their own settings object — a disabled
        traffic spike on 200 environment-fallback apps is 200 alerts not migrated, and
        reporting only the explicit-tier ones understates that by two orders of magnitude.

        `detail` qualifies the reason where there is something useful to say: the KPM for
        a missing-equivalent skip, otherwise the tier the alert resolved from.
        """
        table = {}

        for reason, key_label, detail in self.existing_skips:
            bucket = table.setdefault(reason, {})
            entry = (key_label, detail)
            bucket[entry] = bucket.get(entry, 0) + 1

        for row in self.rows:
            if row.status == STATUS_DISABLED:
                # trafficSpike (and errorRateExceptions/trafficDrop) come from both
                # rum-web and rum-mobile — naming the schema keeps those counts apart
                # instead of silently merging two different objects into one number.
                reason = SKIP_DISABLED_AT_SOURCE
                detail = f"{tier_label(row.source_type)}, {schema_label(row.schema)}"
            elif row.status == STATUS_SKIPPED:
                reason, detail = SKIP_NO_EQUIVALENT, row.kpm or ""
            else:
                continue
            bucket = table.setdefault(reason, {})
            entry = (row.alert_type, detail)
            bucket[entry] = bucket.get(entry, 0) + 1

        return table

    def alert_type_breakdown(self):
        """Return {(alertKey, schema): {source_type: object_count}}.

        Resolution happens per app per classic schema object, not per alert type: every
        alert type bundled in the same schema object moves together as one unit (explicit,
        environment-level, or schema-default). mobileCrash lives in its own schema
        (rum-mobile-crash-rate-increase), separate from the rest of that app's mobile
        alerts (rum-mobile), so it can land on a different tier — that is genuine per-app
        independence, but it is independence between two schema objects, not between
        individual alert keys within one object.

        errorRateExceptions, trafficDrop, and trafficSpike are each produced by both
        rum-web and rum-mobile, so grouping by alert key alone would silently merge two
        different schema objects' counts into one row. Keying by (alert key, schema) keeps
        them apart and makes clear which schema each row's tier actually came from.

        Unlike apps_by_source_type, this is unambiguous: a given app can land in more
        than one source_type bucket (e.g. mobileCrash from an env-level object while its
        other mobile alerts fall back to schema defaults) because those two counts come
        from different schema objects. Breaking the count down by alert type avoids the
        apparent double-counting that shows up when counting apps instead of objects.
        """
        table = {}
        for o in self.health_to_create:
            key = (o["value"]["alertKey"], o["_meta"]["sourceSchema"])
            source_type = o["_meta"]["sourceType"]
            table.setdefault(key, {}).setdefault(source_type, 0)
            table[key][source_type] += 1
        return table
