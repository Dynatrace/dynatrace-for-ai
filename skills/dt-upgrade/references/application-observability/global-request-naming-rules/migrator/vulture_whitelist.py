"""Vulture whitelist — intentionally unused symbols that must not be removed.

  * Pydantic internals in rules/models.py: ``model_config`` and aliased field
    declarations (e.g. ``case_sensitive``) are consumed by Pydantic's metaclass,
    not called directly by application code.
  * Module-level ``__getattr__``: used by Python's import machinery for lazy
    module attributes; vulture does not recognise this special name.
  * MagicMock.return_value / side_effect: standard mock configuration attributes;
    vulture sees assignments as "unused" because the attribute is not read back.

The bare attribute references below are the whitelist itself — that is the format
vulture expects — and the imports are grouped with the references they justify.
"""

# pylint: disable=pointless-statement,wrong-import-position,wrong-import-order

# -- Pydantic internals in rules/models.py (API rule parsing models).
from glob_name_migrator.rules.models import ComparisonInfo, Condition, Rule

ComparisonInfo.model_config
ComparisonInfo.case_sensitive
Condition.model_config
Rule.model_config

# -- Module-level __getattr__ for lazy attribute loading.
from glob_name_migrator.queries import entity, span  # noqa: F401

entity.__getattr__
span.__getattr__

# -- VerificationResult fields that are part of the public result interface even
#    though the current summary reporter does not yet consume every field.
from glob_name_migrator.analysis.overselect_loop import VerificationResult

VerificationResult.entity_negations_applied
VerificationResult.suboptimal_used

# -- MagicMock configuration attributes (unittest.mock).
#    Vulture flags assignments like ``mock.foo.return_value = x`` as unused
#    because the attribute is set but never read back; these are intentional.
from unittest.mock import MagicMock

MagicMock.return_value
MagicMock.side_effect
