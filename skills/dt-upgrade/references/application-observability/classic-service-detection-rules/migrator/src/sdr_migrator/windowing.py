from __future__ import annotations

import re

_WINDOW_RE = re.compile(r"^now\(\)-(\d+)(h|m)$")
_FALLBACK_MINUTES = 120


def parse_window_minutes(window: str) -> int:
    """Parse a ``now()-Nh``/``now()-Nm`` window string into a minute count.

    Falls back to 120 (2h) if the string doesn't match the expected pattern. The
    fallback only affects retry-window arithmetic, never the original window
    string used for the first attempt.
    """
    match = _WINDOW_RE.match(window.strip())
    if not match:
        return _FALLBACK_MINUTES
    value, unit = int(match.group(1)), match.group(2)
    return value * 60 if unit == "h" else value


def _minutes_to_dql(minutes: int) -> str:
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def retry_window(window: str, attempt: int) -> str:
    """Return the DQL ``from:``-clause value for the Nth contiguous shift back.

    ``attempt`` starts at 1. Each attempt covers a window the same duration as
    the original, sliding earlier by one duration per step, with no gaps:
    ``retry_window("now()-2h", 1) == "now()-4h, to:now()-2h"``.
    """
    duration = parse_window_minutes(window)
    end = duration * attempt
    start = duration * (attempt + 1)
    return f"now()-{_minutes_to_dql(start)}, to:now()-{_minutes_to_dql(end)}"
