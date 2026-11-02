"""One pass over the tenant's request attributes."""

from __future__ import annotations

from pathlib import Path

from .attributes.classification import classify_all
from .attributes.reading import read_request_attributes
from .cache import CachingQueryRunner
from .clients.transports import ConfigReader, QueryRunner
from .dql.windowing import QueryWindow
from .emission.artifact import emit_all
from .reconstruction.candidate_search import assess_all
from .reconstruction.harvest import harvest_all
from .reconstruction.resolution import resolve_target_sets
from .reconstruction.verdict import decide_all
from .reporting.outputs import write_outputs
from .run_result import RunResult
from .workdir import DEFAULT_OUTPUT, create_run_workdir


def run_migration(
    config_reader: ConfigReader,
    query_runner: QueryRunner,
    *,
    platform_url: str,
    window: QueryWindow,
    output: Path = DEFAULT_OUTPUT,
) -> RunResult:
    """Read the tenant's request attributes and say what the pass found.

    `platform_url` is carried for provenance on the result rather than to build a request: each
    transport owns its own base URL.
    """
    # One local per stage output, threaded into the next stage and finally into the result. Over
    # pylint's default because the pipeline has that many stages, not because any of them is idle.
    # pylint: disable=too-many-locals
    workdir = create_run_workdir(output)
    # Wrapped here, before anything can ask a question: every later stage is handed the decorator
    # and not the transport, so none of them can spend a read the run already paid for.
    runner = CachingQueryRunner(query_runner, workdir / "cache")
    request_attributes = read_request_attributes(config_reader)
    classifications = classify_all(request_attributes)
    resolutions = resolve_target_sets(runner, classifications, window=window)
    harvests = harvest_all(runner, classifications, resolutions, window=window)
    # Pure computation over the harvest - no query is spent here, which is why the runner is not
    # handed on.
    assessed_candidates = assess_all(resolutions, harvests)
    # The one later stage that may spend a read to decide, so it is handed the runner.
    data_source_verdicts, request_attribute_verdicts = decide_all(
        runner, classifications, resolutions, harvests, assessed_candidates, window=window
    )
    # Pure computation over what the verdicts already decided - no query is spent, so the runner is
    # not handed on. A Request Attribute that earned a body gets an Artifact; a body a validity check
    # refuses becomes a rejection and its Request Attribute is unprocessable.
    artifacts, emission_rejections = emit_all(
        classifications,
        request_attributes,
        data_source_verdicts,
        request_attribute_verdicts,
    )
    result = RunResult(
        request_attributes=request_attributes,
        classifications=classifications,
        resolutions=resolutions,
        harvests=harvests,
        assessed_candidates=assessed_candidates,
        data_source_verdicts=data_source_verdicts,
        request_attribute_verdicts=request_attribute_verdicts,
        artifacts=artifacts,
        emission_rejections=emission_rejections,
        window=window,
        workdir=workdir,
        cache_dir=runner.directory,
        platform_url=platform_url,
    )
    # The run's own directory is the shareable result: the Summary Index a consumer classifies on,
    # the Report a customer reads, and the Artifact bodies both point at, all written here.
    write_outputs(result)
    return result
