"""Migration assessment: can each calculated service metric be migrated on Phase 3?

Runs inside the usage scan, over every metric the tenant defines. Three inputs, no more:

* the classic definition (:mod:`.definitions`),
* the mapping catalog that says which classic elements have a Phase 3 equivalent
  (:mod:`.catalog`), and
* whether the metric still receives data (:mod:`.traffic`).

The output is a verdict per metric plus, where the answer is yes, one OpenPipeline
``metricExtraction`` processor written to disk (:mod:`.assess`). Deployment is out of scope by
decision: no pipeline, no pipeline group, no routing.
"""

from __future__ import annotations

from .assess import (
    PROCESSOR_DIR,
    VERDICTS,
    assess,
    blocking_reasons,
    decisions,
    totals,
    write_processors,
)
from .catalog import load_default_catalog
from .definitions import fetch_definitions
from .traffic import DEFAULT_WINDOW, keys_with_data

__all__ = [
    "DEFAULT_WINDOW",
    "PROCESSOR_DIR",
    "VERDICTS",
    "assess",
    "blocking_reasons",
    "decisions",
    "fetch_definitions",
    "keys_with_data",
    "load_default_catalog",
    "totals",
    "write_processors",
]
