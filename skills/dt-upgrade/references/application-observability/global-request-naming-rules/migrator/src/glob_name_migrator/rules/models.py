"""Pydantic models for Config v1 ``RequestNamingDto`` payloads.

Only the fields we read are typed; everything else is preserved via
``extra="allow"`` so round-tripping a rule back to JSON loses no data.
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ComparisonInfo(BaseModel):
    """The ``comparisonInfo`` object on each condition.

    The Config v1 API uses ``comparison`` for the operator name; some
    snapshots use ``operator`` instead — both are accepted via AliasChoices.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str
    comparison: str = Field(validation_alias=AliasChoices("comparison", "operator"))
    negate: bool = False
    value: Any = None
    values: list[Any] | None = None
    case_sensitive: bool | None = Field(default=None, alias="caseSensitive")


class Condition(BaseModel):
    """A single rule condition with attribute and comparison info."""

    model_config = ConfigDict(extra="allow")

    attribute: str
    comparisonInfo: ComparisonInfo


class Rule(BaseModel):
    """Subset of ``RequestNamingDto`` the migrator inspects."""

    model_config = ConfigDict(extra="allow")

    id: str
    namingPattern: str | None = None
    enabled: bool = True
    conditions: list[Condition] = Field(default_factory=list)
    managementZones: list[str] = Field(default_factory=list)


__all__ = ["ComparisonInfo", "Condition", "Rule"]
