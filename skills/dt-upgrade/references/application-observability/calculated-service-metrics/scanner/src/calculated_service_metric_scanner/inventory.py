"""Discover calculated service metrics available in Grail."""

from __future__ import annotations

from typing import Any

from .shared import FAILED, PARTIAL, SourceResult

INVENTORY_LIMIT = 100_000
INVENTORY_QUERY = f"""fetch metric.series
| filter startsWith(metric.key, "service.")
| dedup metric.key
| fields metric.key
| limit {INVENTORY_LIMIT + 1}"""


def fetch_metric_keys(client) -> tuple[dict[str, dict[str, Any]], SourceResult]:
    """Return Grail metric metadata keyed by ``service.*`` and coverage state.

    Raw HTTP uses the authoritative ``metricsOnGrail`` Configuration API. dtctl
    has no Config API v1 command, so its transport falls back to Grail discovery.
    """
    source = SourceResult(name="grail_metric_inventory")
    fetch_on_grail = getattr(client, "calculated_service_metrics_on_grail", None)
    if fetch_on_grail is not None:
        try:
            rows = fetch_on_grail()
        except Exception as exc:  # noqa: BLE001 - transport errors become report state
            source.degrade(FAILED, f"listing metrics enabled on Grail failed: {exc}")
            return {}, source

        metrics: dict[str, dict[str, Any]] = {}
        for row in rows:
            classic_key = row.get("id")
            if not isinstance(classic_key, str) or not classic_key.startswith("calc:service."):
                continue
            metric_key = classic_key.removeprefix("calc:")
            metrics[metric_key] = {
                "metric_key": metric_key,
                "classic_metric_key": classic_key,
                "name": row.get("name") if isinstance(row.get("name"), str) else "",
            }
        source.items_checked = len(metrics)
        source.reason = "Configuration API metricsOnGrail"
        return metrics, source

    try:
        rows = client.dql(INVENTORY_QUERY, max_records=INVENTORY_LIMIT + 1)
    except Exception as exc:  # noqa: BLE001 - transport errors become report state
        source.degrade(FAILED, f"querying Grail metric inventory failed: {exc}")
        return {}, source

    truncated = len(rows) > INVENTORY_LIMIT
    keys = {
        value: {"metric_key": value, "classic_metric_key": "calc:" + value, "name": ""}
        for row in rows[:INVENTORY_LIMIT]
        if isinstance(row, dict)
        for value in [_metric_key(row)]
        if value is not None and value.startswith("service.")
    }
    source.items_checked = len(keys)
    source.reason = "Grail metric.series fallback (dtctl transport)"
    source.degrade(
        PARTIAL,
        "Grail metric.series fallback is timeframe-bound; use the HTTP transport with "
        "ReadConfig for the authoritative metricsOnGrail inventory",
    )
    if truncated:
        source.degrade(
            PARTIAL,
            f"Grail inventory exceeded {INVENTORY_LIMIT} service.* keys; results were truncated",
        )
    return keys, source


def _metric_key(row: dict[str, Any]) -> str | None:
    value = row.get("metric.key")
    return value if isinstance(value, str) else None
