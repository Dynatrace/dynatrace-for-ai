"""Settings schema IDs shared by the fetch and translation layers."""

SCHEMA_RUM_WEB = "builtin:anomaly-detection.rum-web"
SCHEMA_RUM_MOBILE = "builtin:anomaly-detection.rum-mobile"
SCHEMA_RUM_MOBILE_CRASH = "builtin:anomaly-detection.rum-mobile-crash-rate-increase"
SCHEMA_KPM_LOAD = "builtin:rum.web.key-performance-metric-load-actions"
SCHEMA_KPM_XHR = "builtin:rum.web.key-performance-metric-xhr-actions"
SCHEMA_FRONTEND_ALERT = "builtin:health-experience.frontend-alert"
SCHEMA_CUSTOM_ALERT = "builtin:davis.anomaly-detectors"

SOURCE_SCHEMAS = [
    SCHEMA_RUM_WEB,
    SCHEMA_RUM_MOBILE,
    SCHEMA_RUM_MOBILE_CRASH,
    SCHEMA_KPM_LOAD,
    SCHEMA_KPM_XHR,
]

ALL_SCHEMAS = SOURCE_SCHEMAS + [SCHEMA_FRONTEND_ALERT]
