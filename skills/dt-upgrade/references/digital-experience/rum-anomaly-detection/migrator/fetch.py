"""
Fetches all source data from Dynatrace and returns it in memory.
"""

from schema_ids import (
    ALL_SCHEMAS,
    SCHEMA_CUSTOM_ALERT,
    SCHEMA_FRONTEND_ALERT,
    SCHEMA_KPM_LOAD,
    SCHEMA_KPM_XHR,
    SCHEMA_RUM_MOBILE,
    SCHEMA_RUM_MOBILE_CRASH,
    SCHEMA_RUM_WEB,
)

# (schema id, use environment object when the filtered app has none of its own)
WEB_SOURCES = [
    (SCHEMA_RUM_WEB, True),
    (SCHEMA_KPM_LOAD, False),
    (SCHEMA_KPM_XHR, False),
]

MOBILE_SOURCES = [
    (SCHEMA_RUM_MOBILE, True),
    (SCHEMA_RUM_MOBILE_CRASH, True),
]


def fetch_source_settings(client, app_filter=None):
    """Return {schema id: settings objects} for the schemas that apply."""
    is_web = app_filter is None or app_filter.startswith("APPLICATION-")
    is_mobile = app_filter is None or app_filter.startswith("MOBILE_APPLICATION-")

    sources = (WEB_SOURCES if is_web else []) + (MOBILE_SOURCES if is_mobile else [])

    raw = {}
    for schema_id, env_fallback in sources:
        print(f"Fetching {schema_id} objects...")
        raw[schema_id] = _scoped_items(client.get_settings(schema_id), app_filter, env_fallback)
    return raw


def _scoped_items(items, app_filter, env_fallback):
    if not app_filter:
        return items
    explicit = [o for o in items if o.get("scope") == app_filter]
    if explicit or not env_fallback:
        return explicit
    return [o for o in items if o.get("scope") == "environment"]


def fetch_classic_to_frontend_id_map(client):
    """(classic id -> FRONTEND id, classic id -> frontend name) for every mapped app."""
    print("Fetching APPLICATION → FRONTEND entity ID mapping...")
    records = client.query(
        'smartscapeNodes "FRONTEND" | fields { toString(id), alias:id }, id_classic, name | limit 10000'
    )
    mapping = {r["id_classic"]: r["id"] for r in records if r.get("id_classic") and r.get("id")}
    names = {r["id_classic"]: r["name"] for r in records if r.get("id_classic") and r.get("name")}
    print(f"  Mapped {len(mapping)} classic entity IDs to FRONTEND IDs")
    return mapping, names


def fetch_existing_frontend_alerts(client, app_filter, classic_to_frontend):
    print("Fetching existing frontend-alert objects from 3rd gen...")
    all_items = client.get_settings(SCHEMA_FRONTEND_ALERT)
    if app_filter:
        frontend_id = (classic_to_frontend or {}).get(app_filter)
        all_items = [
            o for o in all_items
            if app_filter in o.get("value", {}).get("frontends", [])
            or (frontend_id and frontend_id in o.get("value", {}).get("frontends", []))
        ]
    print(f"  Found {len(all_items)} existing object(s)")
    return all_items


def fetch_existing_custom_alerts(client):
    """Custom metric alerts already on the tenant, for apply-time duplicate detection."""
    items = client.get_settings(SCHEMA_CUSTOM_ALERT)
    print(f"  Found {len(items)} existing custom alert(s)")
    return items


def fetch_schemas(client):
    """Fetch every schema definition and return {schema id: schema dict}."""
    print(f"Fetching {len(ALL_SCHEMAS)} schema(s)...")
    return {schema_id: client.get_settings_schema(schema_id) for schema_id in ALL_SCHEMAS}
