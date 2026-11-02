"""The one stretch of time every query of a run asks about."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

DEFAULT_QUERY_WINDOW = "2h"

_EXPRESSION = re.compile(r"^(\d+)([mhd])$")

# The unit letter an expression is written with, as the `timedelta` keyword it means.
_UNIT_SPANS = {"m": "minutes", "h": "hours", "d": "days"}


class QueryWindowError(ValueError):
    pass


@dataclass(frozen=True)
class QueryWindow:
    """The one stretch of time a run asks about, resolved to an absolute pair.

    Resolved once, when the window is made, and every query of the run is bounded by that same
    pair. Rendered as timestamps rather than as `now()`: a run's reads are minutes apart and
    `now()` re-resolves server-side on every one of them, so a process group that left the stretch
    between two reads would read as one the replacement no longer selects. The resolved pair is
    also what a run has to record about itself.
    """

    expression: str
    amount: int
    unit: str
    anchor: datetime

    @property
    def start(self) -> datetime:
        return self.anchor - self._span

    @property
    def end(self) -> datetime:
        return self.anchor

    @property
    def timeframe(self) -> str:
        """The `fetch` clause this window renders, which is part of every query's cache key."""
        return f"from:{_rendered(self.start)}, to:{_rendered(self.end)}"

    @property
    def _span(self) -> timedelta:
        return timedelta(**{_UNIT_SPANS[self.unit]: self.amount})


def _rendered(moment: datetime) -> str:
    return '"' + moment.isoformat().replace("+00:00", "Z") + '"'


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_query_window(text: str, *, now: Callable[[], datetime] = _utc_now) -> QueryWindow:
    match = _EXPRESSION.match(text.strip())
    if match is None:
        raise QueryWindowError(
            f"unrecognised query window {text!r}: give a whole number followed by "
            f"m (minutes), h (hours) or d (days), for example 30m, 2h or 7d"
        )
    return QueryWindow(text.strip(), int(match.group(1)), match.group(2), _anchored(now()))


def _anchored(moment: datetime) -> datetime:
    """The instant a window hangs off, in UTC and to the second.

    Whole seconds because the anchor is rendered into the query text and the query text is the
    cache key: sub-second precision would only make two keys of one question.
    """
    return moment.astimezone(timezone.utc).replace(microsecond=0)
