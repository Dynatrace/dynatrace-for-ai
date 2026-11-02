"""Runtime configuration: CLI/env parsing, output directory, secrets handling.

Two tenant URLs are tracked because the classic Config v1 API and the
platform DQL API often live on different hosts (``<env>.dynatracelabs.com`` vs
``<env>.apps.dynatracelabs.com``). When the user only provides one,
``platform_url`` is derived from ``classic_url`` (inject ``.apps.``) or vice
versa, matching the standard naming convention.

Authentication: a single Dynatrace platform token (``dt0s16.*``) carrying both
the classic ``ReadConfig`` scope and the platform ``storage:*:read`` scopes.
The same token is sent as ``Api-Token`` to Config v1 and as ``Bearer`` to the
platform storage query API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Resolved configuration for a migrator run.

    Secrets are stored as plain strings but ``__repr__`` masks them so they
    cannot leak via accidental logging.
    """

    classic_url: str  # for Config v1 REST
    platform_url: str  # for DQL storage query API
    platform_token: str  # dt0s16.* token used for both APIs
    output_dir: Path
    rule_ids: list[str] | None = None
    query_timeframe: str | None = None  # e.g. "from:now()-2h, to:now()"

    _secret_fields: tuple[str, ...] = field(default=("platform_token",), repr=False)

    def __repr__(self) -> str:  # pragma: no cover - trivial formatting
        masked = {
            "classic_url": self.classic_url,
            "platform_url": self.platform_url,
            "platform_token": _mask(self.platform_token),
            "output_dir": str(self.output_dir),
            "rule_ids": self.rule_ids,
        }
        return f"AppConfig({masked})"


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}...{value[-2:]}"


def default_output_dir(now: datetime | None = None, root: Path | None = None) -> Path:
    """Default output dir uses the invocation UTC timestamp."""

    now = now or datetime.now(timezone.utc)
    root = root or Path.cwd() / "workdir"
    stamp = now.strftime("%Y%m%d-%H%M%S")
    return root / f"run-{stamp}"


def resolve_output_dir(cli_value: str | None) -> Path:
    """Pick an output dir: CLI > env (``GNM_OUTPUT_DIR``) > timestamped default."""

    if cli_value:
        return Path(cli_value).expanduser().resolve()
    env_value = os.environ.get("GNM_OUTPUT_DIR")
    if env_value:
        return Path(env_value).expanduser().resolve()
    return default_output_dir().resolve()


def ensure_workdir(output_dir: Path) -> dict[str, Path]:
    """Create the standard workdir subfolders. Returns their paths."""

    paths = {
        "root": output_dir,
        "cache": output_dir / "cache",
        "derived": output_dir / "derived",
        "report": output_dir / "report",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def derive_url_pair(*, tenant: str | None, classic: str | None, platform: str | None) -> tuple[str, str]:
    """Derive the (classic, platform) URL pair from any of the three inputs.

    Priority: explicit ``classic``/``platform`` flags > generic ``tenant``.
    When only one of ``classic``/``platform`` is given, the other is derived
    by inserting/removing the ``.apps`` infix used by Dynatrace hostnames.
    """

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
    return classic.replace(".dynatracelabs.com", ".apps.dynatracelabs.com").replace(
        ".dynatrace.com", ".apps.dynatrace.com"
    )


def _infer_classic(platform: str) -> str:
    return platform.replace(".apps.dynatracelabs.com", ".dynatracelabs.com").replace(
        ".apps.dynatrace.com", ".dynatrace.com"
    )


class ConfigError(ValueError):
    """Raised when required configuration is missing or malformed."""


def from_cli_and_env(  # pylint: disable=too-many-arguments
    *,
    tenant: str | None = None,
    classic_url: str | None = None,
    platform_url: str | None = None,
    platform_token: str | None = None,
    output_dir: str | None = None,
    rule_ids: list[str] | None = None,
    query_timeframe: str | None = None,
) -> AppConfig:
    """Build an :class:`AppConfig` from CLI flags falling back to env vars.

    Environment variables:
      - ``DT_TENANT`` / ``DT_CLASSIC_URL`` / ``DT_PLATFORM_URL``
      - ``DT_PLATFORM_TOKEN``
      - ``GNM_OUTPUT_DIR``
    """

    resolved_tenant = tenant or os.environ.get("DT_TENANT")
    resolved_classic = classic_url or os.environ.get("DT_CLASSIC_URL")
    resolved_platform = platform_url or os.environ.get("DT_PLATFORM_URL")
    classic, platform = derive_url_pair(
        tenant=resolved_tenant, classic=resolved_classic, platform=resolved_platform
    )

    resolved_token = platform_token or os.environ.get("DT_PLATFORM_TOKEN")
    if not resolved_token:
        raise ConfigError(
            "missing platform token (provide --platform-token or set DT_PLATFORM_TOKEN). "
            "Must be a dt0s16.* token with both ReadConfig and storage:*:read scopes."
        )
    if not resolved_token.startswith("dt0s16."):
        raise ConfigError(
            "platform token must start with 'dt0s16.' "
            "(classic Api-Tokens are not supported in this iteration)."
        )

    return AppConfig(
        classic_url=classic,
        platform_url=platform,
        platform_token=resolved_token,
        output_dir=resolve_output_dir(output_dir),
        rule_ids=rule_ids,
        query_timeframe=query_timeframe,
    )
