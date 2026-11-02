from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CacheStats:
    total: int = 0
    hits: int = 0
    misses: int = 0
    # Live per-query event stream: (query_text, is_hit). Captured on every call
    # because the on-disk cache stores only result rows keyed by a hash of the
    # query, so the query text cannot be recovered after the run.
    query_events: list[tuple[str, bool]] = field(default_factory=list)


class CachingDqlClient:
    """Intra-run caching decorator over a DQL client.

    Wraps any object exposing ``execute(query, *, timeout_seconds=...)`` and
    memoises its rows keyed by a stable hash of the (canonical) query string.
    Reuse is within-run only: the cache lives for the lifetime of this wrapper.
    """

    def __init__(self, inner: Any, cache_dir: Path) -> None:
        self._inner = inner
        self._cache_dir = cache_dir
        self._memory: dict[str, list[dict]] = {}
        self.stats = CacheStats()

    def execute(self, query: str, *, timeout_seconds: float = 300.0) -> list[dict]:
        key = _query_key(query)
        self.stats.total += 1
        if key in self._memory:
            self.stats.hits += 1
            self.stats.query_events.append((query, True))
            return self._memory[key]
        cached = self._read_file(key)
        if cached is not None:
            self.stats.hits += 1
            self.stats.query_events.append((query, True))
            self._memory[key] = cached
            return cached
        self.stats.misses += 1
        self.stats.query_events.append((query, False))
        rows = self._inner.execute(query, timeout_seconds=timeout_seconds)
        self._memory[key] = rows
        self._write_file(key, rows)
        return rows

    def _path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def _read_file(self, key: str) -> list[dict] | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_file(self, key: str, rows: list[dict]) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def _query_key(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
