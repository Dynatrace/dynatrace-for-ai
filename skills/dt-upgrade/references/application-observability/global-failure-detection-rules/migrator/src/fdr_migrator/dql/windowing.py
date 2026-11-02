"""The query window every query runs over."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

DEFAULT_QUERY_WINDOW = "2h"

_EXPRESSION = re.compile(r"^(\d+)([mhd])$")

# The unit letters an expression is written with, as the `timedelta` keyword each one means.
_UNIT_SPANS = {"m": "minutes", "h": "hours", "d": "days"}


class QueryWindowError(ValueError):
    pass


@dataclass(frozen=True)
class QueryWindow:
    """The one stretch of time a run asks about.

    Fixed when the query window is made, and every query of the run is bounded by that same one. The
    query resolving what a rule selects and the query proving a replacement are minutes apart, so
    a timeframe re-read per query would move between them - and a service that left the stretch
    would read as one the replacement no longer selects.
    """

    expression: str
    amount: int
    unit: str
    anchor: datetime

    @property
    def timeframe(self) -> str:
        return f"from:{self._ago(1)}, to:{self._ago(0)}"

    def _ago(self, windows: int) -> str:
        moment = self.anchor - self._span * windows
        return '"' + moment.isoformat().replace("+00:00", "Z") + '"'

    @property
    def _span(self) -> timedelta:
        return timedelta(**{_UNIT_SPANS[self.unit]: self.amount})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_query_window(text: str, *, now: Callable[[], datetime] = _utc_now) -> QueryWindow:
    """The query window an expression names, anchored to the instant the run started.

    Anchored once, here, which is what makes every query of the run ask about the same stretch.
    """
    match = _EXPRESSION.match(text.strip())
    if match is None:
        # Never a silent fallback to a default duration: a run that quietly resolves its Target
        # Sets over a timeframe nobody asked for answers a question that was not put to it.
        raise QueryWindowError(
            f"unrecognised query window {text!r}: give a whole number followed by "
            f"m (minutes), h (hours) or d (days), for example 30m, 2h or 7d"
        )
    return QueryWindow(text.strip(), int(match.group(1)), match.group(2), _anchored(now()))


def _anchored(moment: datetime) -> datetime:
    """The instant a query window hangs off, in UTC and to the second.

    Whole seconds because the anchor is rendered into the query text and the query text is the
    cache key: sub-second precision would only make two keys of one question.
    """
    return moment.astimezone(timezone.utc).replace(microsecond=0)
