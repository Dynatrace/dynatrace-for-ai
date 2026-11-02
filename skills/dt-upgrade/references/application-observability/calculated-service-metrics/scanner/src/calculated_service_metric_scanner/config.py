"""Runtime configuration and output-directory handling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .shared import ConfigError, derive_url_pair, report_ui_url

DEFAULT_DIR_NAME = "calculated-service-metric-report"


@dataclass(frozen=True)
class AppConfig:
    output_dir: Path
    transport: str = "dtctl"
    dtctl_context: str | None = None
    tenant_label: str = ""
    ui_url: str = ""
    classic_url: str = ""
    platform_url: str = ""
    platform_token: str = ""
    timeout: int = 60
    max_workers: int = 10


def resolve_output_dir(value: str | None, timestamped: bool = False) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    env_value = os.environ.get("CSM_OUTPUT_DIR")
    if env_value:
        return Path(env_value).expanduser().resolve()
    suffix = ""
    if timestamped:
        suffix = "-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return (Path.cwd() / f"{DEFAULT_DIR_NAME}{suffix}").resolve()


def for_dtctl(
    *,
    context: str | None,
    ui_url: str | None,
    output_dir: str | None,
    timestamped: bool,
    timeout: int,
    max_workers: int,
) -> AppConfig:
    from .shared import DtctlError, resolve_context

    try:
        name, environment = resolve_context(context)
    except DtctlError as exc:
        raise ConfigError(str(exc)) from exc
    return AppConfig(
        output_dir=resolve_output_dir(output_dir, timestamped),
        transport="dtctl",
        dtctl_context=name,
        tenant_label=environment or name,
        ui_url=report_ui_url({}, ui_url or environment),
        timeout=timeout,
        max_workers=max_workers,
    )


def for_http(
    *,
    tenant: str | None,
    classic_url: str | None,
    platform_url: str | None,
    ui_url: str | None,
    platform_token: str | None,
    output_dir: str | None,
    timestamped: bool,
    timeout: int,
    max_workers: int,
) -> AppConfig:
    classic, platform = derive_url_pair(
        tenant=tenant or os.environ.get("DT_TENANT"),
        classic=classic_url or os.environ.get("DT_CLASSIC_URL"),
        platform=platform_url or os.environ.get("DT_PLATFORM_URL"),
    )
    token = platform_token or os.environ.get("DT_PLATFORM_TOKEN")
    if not token:
        raise ConfigError("missing platform token; set DT_PLATFORM_TOKEN or use --platform-token")
    if not token.startswith("dt0s16."):
        raise ConfigError("platform token must start with 'dt0s16.'")
    return AppConfig(
        output_dir=resolve_output_dir(output_dir, timestamped),
        transport="http",
        tenant_label=platform,
        ui_url=report_ui_url({}, ui_url or platform),
        classic_url=classic,
        platform_url=platform,
        platform_token=token,
        timeout=timeout,
        max_workers=max_workers,
    )
