"""What vulture cannot see: protocol members, and codes declared before anything assigns them.

Vulture matches by identifier name and has no notion of a `Protocol` implementation or of an enum
member read only through a serialised contract, so both look dead to it. Referencing them here
keeps the scan honest about everything else.
"""

# pylint: disable=pointless-statement
# pyright: reportUnusedExpression=false

from ra_migrator.outcomes import (
    DataSourceOutcome,
    HarvestProvenance,
    NeutralisedUncoverableReason,
    NoVerdictReason,
    RequestAttributeOutcome,
    SelectsNothingReason,
)

# The terminal codes the outcome contract is closed over. Declared now so the code space cannot
# grow into string literals later; assigned by the stages that come after this one.
DataSourceOutcome.COVERED
DataSourceOutcome.CONDITION_DROPPED
DataSourceOutcome.NEUTRALISED_UNCOVERABLE
DataSourceOutcome.NEUTRALISED_OBSOLETE
DataSourceOutcome.EMPTY_TARGET_SET
DataSourceOutcome.NO_VERDICT
DataSourceOutcome.UNPROCESSABLE

RequestAttributeOutcome.COVERED
RequestAttributeOutcome.PARTIALLY_COVERED
RequestAttributeOutcome.NOT_COVERABLE
RequestAttributeOutcome.OBSOLETE
RequestAttributeOutcome.SELECTS_NOTHING
RequestAttributeOutcome.NO_VERDICT
RequestAttributeOutcome.UNPROCESSABLE

# The reason codes each verdict is closed over. One enum per verdict, because a reason that could
# sit under two verdicts would mean the two were not split on a recommended action.
NoVerdictReason.TRUNCATED_VERIFICATION_READ
NoVerdictReason.NO_SPANS_AND_NO_FREE_RUNG
NoVerdictReason.NO_PRIMARY_TAG_KEY_ON_THE_TENANT
NoVerdictReason.SOME_DATA_SOURCE_UNMEASURED

NeutralisedUncoverableReason.REFUTED_ON_EVERY_CANDIDATE
NeutralisedUncoverableReason.NO_CANDIDATE_FITS_A_FREE_SLOT
NeutralisedUncoverableReason.EVERY_CANDIDATE_OVER_SELECTS

SelectsNothingReason.EVERY_TAG_MATCHED_NOTHING
SelectsNothingReason.EVERY_SCOPE_SELECTS_NOTHING

# Which side of the harvest a piece of material came from. Recorded on every harvested item now,
# because what a later stage may claim from it depends on the answer; read by the stage that makes
# those claims.
HarvestProvenance.DISCOVERY_READ
HarvestProvenance.span_material
