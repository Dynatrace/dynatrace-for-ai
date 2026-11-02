"""Locate and re-export the shared dt-upgrade configuration scanner."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_SHARED_DIR = Path(
    os.environ.get("DT_UPGRADE_SHARED_SCRIPTS") or _HERE.parents[4] / "shared-scripts"
)

if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

try:
    from config_scan import (  # noqa: E402
        COMPLETE,
        ConfigError,
        DtctlAuthError,
        DtctlClient,
        DtctlError,
        FAILED,
        HttpClient,
        PARTIAL,
        SHARED_SETTINGS_FIELDS,
        SourceResult,
        add_artifact_links,
        artifact_link,
        derive_url_pair,
        gather_sources,
        is_shared_settings_field,
        normalise_url,
        preflight,
        report_ui_url,
        resolve_context,
        strip_cached_results,
    )
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ModuleNotFoundError(
        f"shared scan layer not found at {_SHARED_DIR}; set DT_UPGRADE_SHARED_SCRIPTS "
        "if the reference tree was rearranged"
    ) from exc

__all__ = [
    "artifact_link",
    "add_artifact_links",
    "COMPLETE",
    "ConfigError",
    "derive_url_pair",
    "DtctlAuthError",
    "DtctlClient",
    "DtctlError",
    "FAILED",
    "gather_sources",
    "HttpClient",
    "is_shared_settings_field",
    "normalise_url",
    "PARTIAL",
    "preflight",
    "report_ui_url",
    "resolve_context",
    "SHARED_SETTINGS_FIELDS",
    "SourceResult",
    "strip_cached_results",
]
