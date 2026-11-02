"""Validates generated health alert objects against the live target schema.

The objects are hand-constructed in translate.py rather than derived from the schema, so
nothing otherwise guarantees they still fit it. Every rule here is read from the fetched
schema — no expected values are duplicated in this file, so a schema change surfaces as a
validation failure rather than silently producing objects the API will reject.
"""

import re

from schema_ids import SCHEMA_FRONTEND_ALERT

_ANALYZER_INPUT_PROPERTY = {
    "AutoAdaptive": "autoAdaptiveAnalyzerInput",
    "SeasonalBaseline": "seasonalBaselineAnalyzerInput",
    "StaticThreshold": "staticThresholdAnalyzerInput",
}


def validate_health_objects(objects, schemas):
    """Return a list of human-readable problems; empty means everything is valid."""
    schema = schemas.get(SCHEMA_FRONTEND_ALERT)
    if not schema:
        return ["target schema was not fetched, cannot validate"]

    properties = schema.get("properties", {})
    alert_keys = _enum_values(schema, properties, "alertKey")
    analyzer_types = _enum_values(schema, properties, "analyzerType")
    frontend_pattern = _frontend_pattern(properties)

    problems = []
    for obj in objects:
        where = _describe(obj)
        value = obj.get("value", {})

        for name in _unknown_properties(value, properties):
            problems.append(f"{where}: unknown property '{name}'")

        alert_key = value.get("alertKey")
        if alert_key not in alert_keys:
            problems.append(f"{where}: alertKey '{alert_key}' is not in the schema enum")

        problems += _validate_frontends(value.get("frontends"), frontend_pattern, where)
        problems += _validate_analyzer(value, schema, analyzer_types, where)

        if not value.get("actor"):
            problems.append(f"{where}: actor is empty")

    return problems


def _describe(obj):
    value = obj.get("value", {})
    frontends = value.get("frontends") or ["<no frontend>"]
    return f"{frontends[0]} {value.get('alertKey', '<no alertKey>')}"


def _enum_values(schema, properties, property_name):
    ref = properties.get(property_name, {}).get("type")
    if not isinstance(ref, dict) or "$ref" not in ref:
        return set()
    enum_name = ref["$ref"].split("/")[-1]
    return {item["value"] for item in schema.get("enums", {}).get(enum_name, {}).get("items", [])}


def _frontend_pattern(properties):
    for constraint in properties.get("frontends", {}).get("items", {}).get("constraints", []):
        if constraint.get("type") == "PATTERN":
            return re.compile(constraint["pattern"])
    return None


def _unknown_properties(value, properties):
    return [name for name in value if name not in properties]


def _validate_frontends(frontends, pattern, where):
    if not frontends:
        return [f"{where}: frontends is empty"]
    problems = []
    for frontend in frontends:
        if pattern and not pattern.match(frontend):
            problems.append(f"{where}: frontend '{frontend}' does not match the schema pattern")
    return problems


def _validate_analyzer(value, schema, analyzer_types, where):
    analyzer_type = value.get("analyzerType")
    if analyzer_type not in analyzer_types:
        return [f"{where}: analyzerType '{analyzer_type}' is not in the schema enum"]

    property_name = _ANALYZER_INPUT_PROPERTY.get(analyzer_type)
    if property_name is None:
        return [f"{where}: no analyzer input property known for '{analyzer_type}'"]

    supplied = value.get(property_name)
    if not supplied:
        return [f"{where}: analyzerType is {analyzer_type} but {property_name} is missing"]

    problems = [f"{where}: has {other} but analyzerType is {analyzer_type}"
                for other in _ANALYZER_INPUT_PROPERTY.values()
                if other != property_name and other in value]

    type_name = schema["properties"][property_name]["type"]["$ref"].split("/")[-1]
    expected = set(schema.get("types", {}).get(type_name, {}).get("properties", {}))
    for missing in sorted(expected - set(supplied)):
        problems.append(f"{where}: {property_name} is missing '{missing}'")
    for unknown in sorted(set(supplied) - expected):
        problems.append(f"{where}: {property_name} has unknown field '{unknown}'")
    return problems
