"""Materialising a run's outputs into its own directory, beside the Artifacts it produced.

Three things land in the run directory: the Summary Index a consuming skill classifies on, the
Report a customer reads, and one Artifact body per Request Attribute that earned one. The Summary
Index is built from the run result and never from the Report - the two are independent renderings of
one run - so a run that renders no Report still writes the same summary.
"""

from __future__ import annotations

import json

from ..run_result import RunResult
from .report import render_report
from .summary import build_summary


def write_outputs(result: RunResult, *, render: bool = True) -> None:
    """Write the Summary Index, the Artifact bodies, and - unless suppressed - the Report."""
    workdir = result.workdir
    (workdir / "summary.json").write_text(
        json.dumps(build_summary(result), indent=2), encoding="utf-8"
    )
    artifacts_dir = workdir / "artifacts"
    for artifact in result.artifacts:
        artifacts_dir.mkdir(exist_ok=True)
        (artifacts_dir / f"{artifact.attribute_id}.json").write_text(
            json.dumps(artifact.replacement_request_attribute_body, indent=2), encoding="utf-8"
        )
    if render:
        (workdir / "report.html").write_text(render_report(result), encoding="utf-8")
