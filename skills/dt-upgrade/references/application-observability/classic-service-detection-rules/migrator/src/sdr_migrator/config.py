from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    classic_url: str
    platform_url: str
    platform_token: str
    classic_token: str
    output_dir: Path
    rule_ids: list[str] | None = None

    _secret_fields: tuple[str, ...] = field(default=("platform_token", "classic_token"), repr=False)

    def __repr__(self) -> str:
        return (
            f"AppConfig(classic_url={self.classic_url!r}, "
            f"platform_url={self.platform_url!r}, "
            f"platform_token={_mask(self.platform_token)!r}, "
            f"classic_token={_mask(self.classic_token)!r}, "
            f"output_dir={str(self.output_dir)!r}, "
            f"rule_ids={self.rule_ids!r})"
        )


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}...{value[-2:]}"


class ConfigError(ValueError):
    pass


def derive_url_pair(*, tenant: str | None, classic: str | None, platform: str | None) -> tuple[str, str]:
    if not (tenant or classic or platform):
        raise ConfigError("missing tenant URL (provide --tenant, --classic-url, or --platform-url)")

    if classic and platform:
        return _normalise(classic), _normalise(platform)
    if classic:
        return _normalise(classic), _normalise(_infer_platform(classic))
    if platform:
        return _normalise(_infer_classic(platform)), _normalise(platform)

    norm = _normalise(tenant)  # type: ignore[arg-type]
    if ".apps." in norm:
        return _infer_classic(norm), norm
    return norm, _infer_platform(norm)


def _normalise(url: str) -> str:
    return url.rstrip("/")


def _infer_platform(classic: str) -> str:
    return (
        classic.replace(".dynatracelabs.com", ".apps.dynatracelabs.com")
               .replace(".dynatrace.com", ".apps.dynatrace.com")
    )


def _infer_classic(platform: str) -> str:
    return (
        platform.replace(".apps.dynatracelabs.com", ".dynatracelabs.com")
                .replace(".apps.dynatrace.com", ".dynatrace.com")
    )


def default_output_dir(now: datetime | None = None, root: Path | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    root = root or Path.cwd() / "workdir"
    stamp = now.strftime("%Y%m%d-%H%M%S")
    return root / f"run-{stamp}"


def resolve_output_dir(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser().resolve()
    env_value = os.environ.get("SDR_OUTPUT_DIR")
    if env_value:
        return Path(env_value).expanduser().resolve()
    return default_output_dir().resolve()


def from_cli_and_env(  # pylint: disable=too-many-arguments
    *,
    tenant: str | None = None,
    classic_url: str | None = None,
    platform_url: str | None = None,
    platform_token: str | None = None,
    classic_token: str | None = None,
    output_dir: str | None = None,
    rule_ids: list[str] | None = None,
) -> AppConfig:
    resolved_tenant = tenant or os.environ.get("DT_TENANT")
    resolved_classic = classic_url or os.environ.get("DT_CLASSIC_URL")
    resolved_platform = platform_url or os.environ.get("DT_PLATFORM_URL")
    classic, platform = derive_url_pair(
        tenant=resolved_tenant, classic=resolved_classic, platform=resolved_platform
    )

    resolved_platform_token = platform_token or os.environ.get("DT_PLATFORM_TOKEN")
    if not resolved_platform_token:
        raise ConfigError(
            "missing platform token (provide --platform-token or set DT_PLATFORM_TOKEN). "
            "Must be a dt0s16.* token."
        )
    if not resolved_platform_token.startswith("dt0s16."):
        raise ConfigError(
            "platform token must start with 'dt0s16.' "
            "(classic Api-Tokens starting with dt0c01. are not supported)."
        )

    resolved_classic_token = classic_token or os.environ.get("DT_CLASSIC_TOKEN")
    if not resolved_classic_token:
        raise ConfigError(
            "missing classic token (provide --classic-token or set DT_CLASSIC_TOKEN). "
            "Must be a dt0c01.* token."
        )
    if not resolved_classic_token.startswith("dt0c01."):
        raise ConfigError(
            "classic token must start with 'dt0c01.' "
            "(platform tokens starting with dt0s16. are not valid here)."
        )

    return AppConfig(
        classic_url=classic,
        platform_url=platform,
        platform_token=resolved_platform_token,
        classic_token=resolved_classic_token,
        output_dir=resolve_output_dir(output_dir),
        rule_ids=rule_ids,
    )
