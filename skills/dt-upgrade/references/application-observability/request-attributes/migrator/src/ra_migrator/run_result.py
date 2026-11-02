"""What one run found, as the value every rendering of it is built from."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .attributes.classification import AttributeClassification
from .reporting.outcomes import AffectedReason, AttributeClass
from .clients.transports import RequestAttributeConfig
from .dql.windowing import QueryWindow
from .emission.artifact import Artifact, EmissionRejection
from .reconstruction.candidate_search import CandidateAssessment
from .reconstruction.verdict import DataSourceVerdict, RequestAttributeVerdict
from .reconstruction.harvest import Harvest
from .reconstruction.resolution import Resolution


@dataclass(frozen=True)
class RunResult:
    """What one run read, and the figures about the pass itself.

    The counts are derived here rather than by whatever prints them, so two renderings of one run
    cannot disagree about what it found.

    One field per stage plus the run's own provenance, and over pylint's default: this is the value
    every rendering is built from, so collapsing two of them to reach eight would make it carry less
    than a run produced.
    """

    # pylint: disable=too-many-instance-attributes

    request_attributes: tuple[RequestAttributeConfig, ...]
    classifications: tuple[AttributeClassification, ...]
    # One row per affected data source: the set its scope selects, or why no set was reached.
    resolutions: tuple[Resolution, ...]
    # One row per data source a replacement is still to be found for: the material every axis
    # yielded, and the read each piece of it came from.
    harvests: tuple[Harvest, ...]
    # One row per harvested data source: which harvested material qualified as a candidate, what
    # was pruned and why, and which data sources still need a verification read.
    assessed_candidates: tuple[CandidateAssessment, ...]
    # One row per resolved Data Source: its terminal verdict, the reason within it, a human detail,
    # and - where covered - the replacement to emit and the read that established the match.
    data_source_verdicts: tuple[DataSourceVerdict, ...]
    # One row per Request Attribute, rolled up from its Data Sources: the migration unit's verdict.
    request_attribute_verdicts: tuple[RequestAttributeVerdict, ...]
    # One Artifact per Request Attribute that earned a body - the wrapper reasoning and the complete
    # replacement `RequestAttributeDto` a customer deploys.
    artifacts: tuple[Artifact, ...]
    # One rejection per Request Attribute whose body failed a validity check: no body was written and
    # the constraint it broke is named.
    emission_rejections: tuple[EmissionRejection, ...]
    window: QueryWindow
    workdir: Path
    # Where this run kept the answers it got, so nothing has to look in the directory to find out.
    cache_dir: Path
    # Which tenant this describes. A run against several of them produces several reports, and one
    # that does not say which is which cannot be read at all.
    platform_url: str

    @property
    def scanned(self) -> int:
        return len(self.request_attributes)

    @property
    def enabled(self) -> int:
        """Of those scanned, how many the tenant has switched on and this run could read."""
        return sum(
            1
            for one in self.classifications
            if one.enabled and one.verdict is not AttributeClass.UNPROCESSABLE
        )

    @property
    def obsolete(self) -> int:
        """Of those enabled, how many capture nothing Phase 3 keeps and are to be deleted."""
        return self._counted(AttributeClass.OBSOLETE)

    @property
    def affected(self) -> int:
        """Of the remainder, how many Phase 3 stops from capturing."""
        return self._counted(AttributeClass.AFFECTED)

    @property
    def affected_by_reason(self) -> dict[AffectedReason, int]:
        """The affected figure split by cause, counting request attributes and not data sources.

        Both reasons are always present, so a run that found none of one still says so - and one
        request attribute carrying two service technologies contributes one.
        """
        return {
            reason: sum(
                1
                for one in self.classifications
                if one.verdict is AttributeClass.AFFECTED and reason in one.reasons
            )
            for reason in AffectedReason
        }

    @property
    def disabled_carrying_deprecated(self) -> int:
        """Switched off, and would not capture if it were switched back on after Phase 3."""
        return sum(
            1
            for one in self.classifications
            if one.verdict is AttributeClass.DISABLED and one.carries_deprecated
        )

    @property
    def unprocessable(self) -> int:
        """Scanned and not classified, so the funnel never shrinks without saying so."""
        return self._counted(AttributeClass.UNPROCESSABLE)

    def _counted(self, verdict: AttributeClass) -> int:
        return sum(1 for one in self.classifications if one.verdict is verdict)
