"""What one run found, as the value every rendering of it is built from."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .dql.queries import TranslatedRule
from .dql.windowing import QueryWindow
from .emission.artifacts import EmittedArtifact
from .reconstruction.replacement import Replacement
from .reconstruction.resolution import ResolvedRule
from .rules.classification import ClassifiedRule, ScanCoverage


@dataclass(frozen=True)
class RunResult:
    """What one run found: every rule it read, and figures about the pass itself."""

    # pylint: disable=too-many-instance-attributes
    rules: tuple[ClassifiedRule, ...]
    coverage: ScanCoverage
    translations: tuple[TranslatedRule, ...]
    resolutions: tuple[ResolvedRule, ...]
    replacements: tuple[Replacement, ...]
    artifacts: tuple[EmittedArtifact, ...]
    window: QueryWindow
    workdir: Path
    # Which tenant this describes. A run against several of them produces several reports, and one
    # that does not say which is which cannot be read at all.
    platform_url: str
    # The two files this run wrote. Named by the run rather than discovered afterwards, so the
    # value carries where they are without anything having to look.
    summary_path: Path
    report_path: Path
    # A run whose tag-key read failed looks otherwise identical to one on a tenant carrying none:
    primary_tags_unavailable: bool = False
    # A capped tag-key read is neither of those: the candidates came from a subset of the keys.
    primary_tag_keys_capped: bool = False
    # Object ids asked for that matched no rule the tenant holds. Kept so a run that reworked
    # fewer rules than it was asked about can say which ones it never saw.
    # Empty on a run over the whole tenant. Non-empty means the findings cover the rules asked
    # for and nothing else, which every rendering has to say out loud.
    requested_rule_ids: tuple[str, ...] = ()
    unmatched_rule_ids: tuple[str, ...] = ()
    # Object ids asked for that name a real rule this run has no findings about, because the rule
    # is disabled or carries nothing deprecated. Told apart from the ids above: the caller got the
    # id right, and there was simply nothing to rework.
    requested_not_affected: tuple[str, ...] = ()
