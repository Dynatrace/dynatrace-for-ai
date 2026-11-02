"""Where one run puts what it produced."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

DEFAULT_OUTPUT = Path("workdir")


class WorkdirError(RuntimeError):
    """The run cannot have a directory of its own."""


def create_run_workdir(
    output: Path = DEFAULT_OUTPUT, *, clock: Callable[[], float] = time.time
) -> Path:
    """A fresh directory for this run, inside the output location given.

    Each run gets its own, and an earlier run's directory is never written into, overwritten or
    removed - which is also what keeps the response cache inside it from outliving the run that
    filled it.
    """
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(clock()))
    run = output / f"run-{stamp}"
    try:
        run.mkdir(parents=True)
    except FileExistsError as clash:
        # Refused rather than reused: a second run writing into the first one's directory would
        # replay the cache it filled and mix the two runs' files, so the answer would describe
        # neither pass.
        raise WorkdirError(f"{run} already exists; a run never writes into another one's") from clash
    return run
