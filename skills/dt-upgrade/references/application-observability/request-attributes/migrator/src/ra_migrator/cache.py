"""The response store one run answers its repeated questions from."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .clients.transports import DqlAnswer, QueryRunner

_DEFAULT_DEADLINE = 300.0


def cache_key(query: str) -> str:
    """The key a query's rows are stored under: the query text itself, digested.

    The text is already the structured key - the window, the filters and the fields are rendered
    into it in a fixed order - so hashing anything else would only spell one question twice.
    """
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:32]


class CachingQueryRunner:
    """Runs queries through another runner, keeping what came back for the rest of the run.

    A decorator rather than a lookup the orchestrator performs: it satisfies the same protocol as
    the runner it wraps, so whatever holds it cannot tell the difference and no later stage can
    route around it.
    """

    def __init__(self, inner: QueryRunner, cache_dir: Path) -> None:
        self._inner = inner
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def directory(self) -> Path:
        return self._dir

    def execute(self, query: str, *, deadline_seconds: float = _DEFAULT_DEADLINE) -> list[dict[str, Any]]:
        return self.answer(query, deadline_seconds=deadline_seconds).records

    def answer(self, query: str, *, deadline_seconds: float = _DEFAULT_DEADLINE) -> DqlAnswer:
        stored = self._dir / f"{cache_key(query)}.json"
        # Looked up directly by key; nothing ever scans the directory.
        if stored.exists():
            return _replayed(json.loads(stored.read_text(encoding="utf-8")))
        answer = self._inner.answer(query, deadline_seconds=deadline_seconds)
        # A failure is raised, never stored and never replayed: a refused read, a timeout and a
        # transport error say something about this attempt, not about the tenant's data.
        # Completeness is stored beside the rows because it is a property of the answer, and rows
        # alone would replay a capped answer as a whole one.
        stored.write_text(
            json.dumps({"records": answer.records, "complete": answer.complete}), encoding="utf-8"
        )
        return answer


def _replayed(stored: Any) -> DqlAnswer:
    """What a stored answer says, with an unstated completeness read as unknown, not as whole.

    Reading a file that does not say so as complete would assert something never measured;
    reading it as capped only understates what is known.
    """
    if isinstance(stored, dict):
        return DqlAnswer(stored["records"], complete=bool(stored["complete"]))
    return DqlAnswer(stored, complete=False)
