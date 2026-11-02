"""Where one run puts what it produced."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

DEFAULT_OUTPUT = Path("workdir")


def create_run_workdir(
    output: Path = DEFAULT_OUTPUT, *, clock: Callable[[], float] = time.time
) -> Path:
    """A fresh directory for this run, inside the output location given.

    Each run gets its own, and an earlier run's directory is never written into, overwritten or
    removed - which is also what keeps the response cache inside it from outliving the run that
    filled it.
    """
    stamp = time.strftime("%Y%m%dT%H%M%S", time.localtime(clock()))
    run = output / f"run-{stamp}"
    run.mkdir(parents=True)
    return run
