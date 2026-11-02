from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .clients.dql import DqlAnswer
from .reconstruction.resolution import QueryOutcome

_DEFAULT_DEADLINE = 300.0


def cache_key(query: str) -> str:
    """The key a query's rows are stored under: the query text itself, digested.

    The text is already the structured key - operator, case handling and window are rendered into
    it in a fixed order - so hashing anything else would only spell one answer twice.
    """
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:32]


class AnsweringQueryRunner(Protocol):
    """A runner that says whether the rows it returned are all of them."""

    def answer(self, query: str, *, deadline_seconds: float = ...) -> DqlAnswer: ...


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0


class CachingQueryRunner:
    """Runs queries through another runner, keeping what came back for the rest of the run."""

    def __init__(self, inner: AnsweringQueryRunner, cache_dir: Path) -> None:
        self._inner = inner
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self.stats = CacheStats()

    def execute(
        self, query: str, *, deadline_seconds: float = _DEFAULT_DEADLINE
    ) -> list[dict[str, Any]]:
        return self.run(query, deadline_seconds=deadline_seconds).records

    def run(self, query: str, *, deadline_seconds: float = _DEFAULT_DEADLINE) -> QueryOutcome:
        stored = self._dir / f"{cache_key(query)}.json"
        # Looked up directly by key; nothing ever scans the directory.
        if stored.exists():
            self.stats.hits += 1
            return _replayed(json.loads(stored.read_text(encoding="utf-8")))
        # A failure is raised, never stored and never replayed: a refused read, a timeout and a
        # transport error say something about this attempt, not about the tenant's data.
        answer = self._inner.answer(query, deadline_seconds=deadline_seconds)
        self.stats.misses += 1
        # Completeness is stored beside the rows because it is a property of the answer: replaying
        # rows alone would report a capped answer as a whole one on every later run.
        stored.write_text(
            json.dumps({"records": answer.records, "complete": answer.complete}), encoding="utf-8"
        )
        return QueryOutcome(answer.records, cache_hit=False, complete=answer.complete)


def _replayed(stored: Any) -> QueryOutcome:
    """What a stored answer says, with an unstated completeness read as unknown, not as whole.

    A file holding the rows alone was written before completeness was recorded, so nothing in it
    says the platform did not cap it. Reading it as complete would assert something never
    measured; reading it as incomplete only understates what is known.
    """
    if isinstance(stored, dict):
        return QueryOutcome(stored["records"], cache_hit=True, complete=bool(stored["complete"]))
    return QueryOutcome(stored, cache_hit=True, complete=False)
