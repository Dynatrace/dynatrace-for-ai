"""The vocabulary a run's affected rules are summarised in, and the mapping onto it.

The buckets are the *grouping* and never the message: one holds several terminal codes, and every
rule carries the exact code it reached alongside the bucket. A reader who cannot tell an empty
scope from a rule selecting only external services cannot tell what to do next.

Kept apart from either rendering so that where a rule lands can be asserted without reading
markup, and so that rewording a report can never move a rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from ..emission.artifacts import EmittedArtifact
from ..reconstruction.replacement import Coverage, NotCoverableReason, Replacement
from ..reconstruction.resolution import ResolutionOutcome, ResolvedRule
from ..rules.classification import ClassifiedRule, RuleStanding, carries_deprecated_condition
from ..run_result import RunResult


class Outcome(StrEnum):
    """Where one affected rule ended, as the code a caller groups on.

    Mutually exclusive and exhaustive over the affected set. Carries no display strings: whatever
    renders it owns the wording, so a report can be reworded without moving a rule.
    """

    COVERED = "covered"
    NOT_COVERABLE = "not-coverable"
    SELECTS_NOTHING = "selects-nothing"
    NO_TRAFFIC = "no-traffic"
    NO_VERDICT = "no-verdict"
    UNPROCESSABLE = "unprocessable"


@dataclass(frozen=True)
class BucketedRule:
    """One affected rule under its bucket, with everything the run learned about it.

    The bucket and the terminal code travel together and neither substitutes for the other.
    """

    rule: ClassifiedRule
    outcome: Outcome
    reason: str
    detail: str = ""
    resolution: ResolvedRule | None = None
    replacement: Replacement | None = None
    artifact: EmittedArtifact | None = None


def bucket_rules(result: RunResult) -> tuple[BucketedRule, ...]:
    """Every rule this run's findings are about, each under exactly one bucket.

    Walked over the rules rather than over the replacements: a rule that never reached a
    resolution has no replacement, and bucketing off the replacements would print a headline
    count above fewer rules than it names.
    """
    resolutions = {resolved.object_id: resolved for resolved in result.resolutions}
    replacements = {replacement.object_id: replacement for replacement in result.replacements}
    artifacts = {artifact.rule_id: artifact for artifact in result.artifacts}
    return tuple(
        _bucketed(
            rule,
            resolutions.get(rule.object_id),
            replacements.get(rule.object_id),
            artifacts.get(rule.object_id),
        )
        for rule in result.rules
        if is_subject(rule)
    )


def bucket_counts(bucketed: Sequence[BucketedRule]) -> dict[Outcome, int]:
    """How many rules each bucket holds, every bucket present and an empty one counted zero."""
    counts = dict.fromkeys(Outcome, 0)
    for entry in bucketed:
        counts[entry.outcome] += 1
    return counts


def codes_of(outcome: Outcome) -> tuple[str, ...]:
    """Every terminal code one bucket holds, which is the contract a caller classifies on.

    Read off the same tables the grouping dispatches through, so what a bucket is documented to
    hold and what it actually holds cannot drift apart.
    """
    held = [Coverage.EXACT.value] if outcome is Outcome.COVERED else []
    held += [
        code.value
        for table in (_STANDING_BUCKETS, _RESOLUTION_BUCKETS, _REASON_BUCKETS)
        for code, bucket in table.items()
        if bucket is outcome
    ]
    # One code arrives from two stages and means the same thing in both, so it is held once.
    return tuple(sorted(dict.fromkeys(held)))


def is_subject(rule: ClassifiedRule) -> bool:
    """Whether the run's findings are about this rule.

    The affected rules, plus the ones the tool could not read: "the tool could not read it" is not
    "it is not affected", and a rule that vanishes from the report is the failure this grouping
    exists to prevent. Both halves require the rule to be enabled, which the second already is -
    a disabled rule is recorded as disabled and nothing else.
    """
    return rule.enabled and (
        carries_deprecated_condition(rule) or rule.standing is RuleStanding.UNCLASSIFIABLE
    )


def _bucketed(
    rule: ClassifiedRule,
    resolution: ResolvedRule | None,
    replacement: Replacement | None,
    artifact: EmittedArtifact | None,
) -> BucketedRule:
    outcome, reason, detail = _grouping(rule, resolution, replacement)
    return BucketedRule(
        rule=rule,
        outcome=outcome,
        reason=reason,
        detail=detail,
        resolution=resolution,
        replacement=replacement,
        artifact=artifact,
    )


def _grouping(
    rule: ClassifiedRule, resolution: ResolvedRule | None, replacement: Replacement | None
) -> tuple[Outcome, str, str]:
    if rule.standing in _STANDING_BUCKETS:
        # Neither of these reaches a resolution, so the standing is the whole of the outcome.
        return _STANDING_BUCKETS[rule.standing], rule.standing.value, ""
    if replacement is not None:
        # The reason before the coverage, always. The reason that says the tool failed ships with
        # a not-coverable coverage, so reading the coverage first would group every failed rule
        # among the ones a human is asked to rework - a rework task nobody can carry out.
        if replacement.reason is not None:
            return (
                _REASON_BUCKETS[replacement.reason],
                replacement.reason.value,
                replacement.detail,
            )
        if replacement.coverage is Coverage.EXACT:
            return Outcome.COVERED, Coverage.EXACT.value, replacement.detail
        return Outcome.UNPROCESSABLE, NotCoverableReason.ERROR.value, _NO_REASON
    if resolution is not None and resolution.outcome in _RESOLUTION_BUCKETS:
        return (
            _RESOLUTION_BUCKETS[resolution.outcome],
            resolution.outcome.value,
            resolution.detail,
        )
    return Outcome.UNPROCESSABLE, ResolutionOutcome.ERROR.value, _NOT_REACHED


_STANDING_BUCKETS: dict[RuleStanding, Outcome] = {
    # An unknown attribute or predicate shape is not something a tenant administrator can fix by
    # editing the rule, and no re-run changes it. That is what separates this from a measurement
    # that failed, where a narrower window or a smaller scope genuinely might.
    RuleStanding.UNCLASSIFIABLE: Outcome.UNPROCESSABLE,
    # The rule is skipped whole already today, so it targets nothing before anything changes.
    RuleStanding.DEAD_TODAY: Outcome.SELECTS_NOTHING,
}

_RESOLUTION_BUCKETS: dict[ResolutionOutcome, Outcome] = {
    # Nothing was asked about this rule, so nothing may be said about its traffic or about what
    # it targets. What it needs is the same hand rework as a measured rule nothing could cover.
    ResolutionOutcome.UNTRANSLATABLE: Outcome.NOT_COVERABLE,
    # These two mean the rule is dead configuration before anything changes. One is decided
    # without a query and the other after one; they differ in cost, not in what to do about them.
    ResolutionOutcome.MATCHES_NOTHING: Outcome.SELECTS_NOTHING,
    ResolutionOutcome.EMPTY_SCOPE: Outcome.SELECTS_NOTHING,
    # The weakest fit of the three, because the rule does select something - but what it selects
    # is outside what this tool governs, so there is still nothing to rework. Its own code line is
    # what keeps the difference readable.
    ResolutionOutcome.ONLY_EXTERNAL: Outcome.SELECTS_NOTHING,
    # The rule targets services; they were simply idle. Kept apart from the three above, because
    # collapsing them is how a rule targeting nothing is handed over as if it merely lacked
    # traffic.
    ResolutionOutcome.DORMANT: Outcome.NO_TRAFFIC,
    ResolutionOutcome.INCOMPLETE_READ: Outcome.NO_VERDICT,
    ResolutionOutcome.QUERY_TOO_LARGE: Outcome.NO_VERDICT,
    ResolutionOutcome.ERROR: Outcome.UNPROCESSABLE,
    # RESOLVED is deliberately absent: a resolved rule goes on to a replacement, so it is not a
    # terminal state and reaching here with one is this tool's problem rather than a finding.
}

_REASON_BUCKETS: dict[NotCoverableReason, Outcome] = {
    NotCoverableReason.OVER_SELECTING: Outcome.NOT_COVERABLE,
    NotCoverableReason.SERVICE_TYPE_ONLY: Outcome.NOT_COVERABLE,
    NotCoverableReason.EMPTY_REPLACEMENT: Outcome.NOT_COVERABLE,
    NotCoverableReason.NO_EXPRESSIBLE_CANDIDATE: Outcome.NOT_COVERABLE,
    NotCoverableReason.TOO_MANY_CONDITIONS: Outcome.NOT_COVERABLE,
    # Neither of these says anything about the rule, and both call for someone to read the run
    # instead. Folded in above, they would hand out a rework task for a rule that may well be
    # coverable once a read is not capped.
    NotCoverableReason.UNVERIFIED: Outcome.NO_VERDICT,
    NotCoverableReason.UNDER_SELECTING: Outcome.NO_VERDICT,
    NotCoverableReason.ERROR: Outcome.UNPROCESSABLE,
}

# A verdict withheld with no reason attached. Not a finding about the rule: this tool assembled a
# state it has no reading for, which is the same class of thing as failing outright.
_NO_REASON = "no reason was recorded for withholding the replacement"

# An affected rule the run produced no resolution for. Not a finding about the rule: nothing was
# measured, so there is nothing the rule's owner could act on.
_NOT_REACHED = "the run produced no resolution for this rule, so nothing about it was measured"
