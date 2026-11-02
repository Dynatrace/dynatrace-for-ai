"""Resolve explicitly referenced classic queue IDs through DQL."""

from __future__ import annotations

from typing import Any

from .shared import FAILED, SourceResult

_CHUNK_SIZE = 100


def fetch_queues(client, queue_ids: set[str]) -> tuple[dict[str, dict[str, Any]], SourceResult]:
    source = SourceResult(name="queue_lookup", items_checked=len(queue_ids))
    if not queue_ids:
        source.reason = "not needed (no queue IDs referenced)"
        return {}, source

    records: dict[str, dict[str, Any]] = {}
    ordered = sorted(queue_ids)
    try:
        for start in range(0, len(ordered), _CHUNK_SIZE):
            chunk = ordered[start : start + _CHUNK_SIZE]
            values = ", ".join(f'"{queue_id}"' for queue_id in chunk)
            query = (
                "fetch dt.entity.queue"
                f" | filter in(id, array({values}))"
                " | fields id, entity.name, queueName, queueDestinationType, queueVendorName"
            )
            for row in client.dql(query, max_records=len(chunk)):
                queue_id = row.get("id")
                if not queue_id:
                    continue
                records[queue_id] = {
                    "id": queue_id,
                    "name": row.get("entity.name") or row.get("queueName") or queue_id,
                    "queue_name": row.get("queueName"),
                    "destination_type": row.get("queueDestinationType"),
                    "vendor": row.get("queueVendorName"),
                    "resolved": True,
                }
    except Exception as exc:  # noqa: BLE001 - detection remains valid without enrichment
        source.degrade(FAILED, f"queue entity lookup failed: {exc}")
        return records, source

    missing = len(queue_ids - set(records))
    if missing:
        source.reason = f"{missing}/{len(queue_ids)} referenced queue IDs no longer resolved"
    return records, source
