"""Which calculated service metrics still receive data.

A dormant metric is not a migration problem. Generating a processor for it produces a permanently
empty metric, and the customer's question is whether the metric is still wanted at all.

This is answered by asking the **metric index**, in one query for the whole environment: which
``service.*`` keys hold a series in the window. The index is metadata, so the query scans no bytes
and answers for hundreds of metrics in seconds. An earlier design inferred dormancy from spans —
whether any span satisfied the metric's conditions — which cost one span query per metric and only
covered the metrics that happened to carry a ``SERVICE_TYPE`` condition.

Two tenant limits shape this, both measured rather than assumed:

* **``fetch metric.series`` reaches back 10 days and no further.** A longer window is rejected
  outright — *``…`` isn't a valid timeframe: only last 10 days data is allowed* — so the window is
  capped, and a longer one is refused here with that explanation rather than as a bare HTTP 400.
* **``timeseries`` is not an alternative for a whole environment.** It reaches back much further,
  but a statement may name at most 10 metric keys (*TOO_MANY_METRIC_KEYS_IN_TIMESERIES*) and a
  single key over a long window is slow, so covering a few hundred metrics that way means dozens
  of batched queries for a more precise answer to a question the 10-day window already answers
  well enough. Spot-checked against a live environment: of the metrics the index reported as
  having no recent data, some have no series at all and the rest last produced data months
  back.
"""

from __future__ import annotations

import re

from ..shared import FAILED, SourceResult

#: The longest window ``fetch metric.series`` accepts. Also the default: a shorter window makes a
#: normal but infrequent metric look dormant.
DEFAULT_WINDOW = "10d"
MAX_WINDOW_DAYS = 10
SERIES_LIMIT = 100_000

_WINDOW = re.compile(r"(\d+)([mhd])")


def window_days(window: str) -> float | None:
    """*window* in days, or ``None`` when it is not a shape this code can check."""
    match = _WINDOW.fullmatch(window.strip())
    if not match:
        return None
    size, unit = int(match.group(1)), match.group(2)
    return size * {"m": 1 / 1440, "h": 1 / 24, "d": 1.0}[unit]


def _query(window: str) -> str:
    return f"""fetch metric.series, from: now()-{window}
| filter startsWith(metric.key, "service.")
| dedup metric.key
| fields metric.key
| limit {SERIES_LIMIT}"""


def keys_with_data(client, window: str = DEFAULT_WINDOW) -> tuple[set[str], SourceResult]:
    """Grail-form keys (``service.<key>``) that hold a series in *window*.

    A failure returns an empty set with a failed state, and the caller must then report the
    traffic state as unknown. Treating an unanswered query as "no data" would tell a customer to
    review metrics that are working.
    """
    source = SourceResult(name="calculated_metric_traffic")
    source.reason = f"metric.series over the last {window}"
    days = window_days(window)
    if days is not None and days > MAX_WINDOW_DAYS:
        source.degrade(
            FAILED,
            f"a {window} window cannot be read: the metric series index holds the last "
            f"{MAX_WINDOW_DAYS} days only, so --traffic-window must not exceed "
            f"{MAX_WINDOW_DAYS}d",
        )
        return set(), source
    try:
        rows = client.dql(_query(window), max_records=SERIES_LIMIT)
    except Exception as exc:  # noqa: BLE001 - transport errors become report state
        source.degrade(FAILED, f"reading calculated service metric datapoints failed: {exc}")
        return set(), source
    keys = {
        row["metric.key"]
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("metric.key"), str)
    }
    source.items_checked = len(keys)
    return keys, source
