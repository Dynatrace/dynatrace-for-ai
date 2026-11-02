"""What a run needs to know before it can read anything: which hosts, and with what credential."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

# The platform token is accepted from this environment variable and from nowhere else.
_TOKEN_VAR = "DT_PLATFORM_TOKEN"
_TOKEN_PREFIX = "dt0s16."
_CLASSIC_TOKEN_PREFIX = "dt0c01."

_TOKEN_SCOPES = "ReadConfig, storage:spans:read, storage:entities:read"

# The classic host and the platform host of one tenant, as the pair of infixes that tell them
# apart. Either can be given and the other follows; both can be given and neither is derived.
_HOST_PAIRS = (
    (".live.dynatrace.com", ".apps.dynatrace.com"),
    (".dev.dynatracelabs.com", ".dev.apps.dynatracelabs.com"),
)


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SecretToken:
    """A credential that cannot be printed by accident.

    Masking one config object's `__repr__` would cover that object alone, while the token also
    travels into client constructors, log lines and exception text. Wrapping it makes the safe
    rendering the default and forces every real use through :meth:`reveal`.
    """

    _value: str

    def reveal(self) -> str:
        return self._value

    def redact(self, text: str) -> str:
        """Replace any occurrence of the raw value in *text* with the masked form.

        An upstream can put the `Authorization` header into a *transport* error message, which
        never passes through the error-hint allowlist. Redaction runs before truncation, so a cut
        cannot leave a usable fragment behind.
        """
        return text.replace(self._value, repr(self)) if self._value else text

    def __repr__(self) -> str:
        prefix, _, _ = self._value.partition(".")
        return f"{prefix}.***" if prefix else "***"

    __str__ = __repr__


@dataclass(frozen=True)
class AppConfig:
    """The two hosts one token reaches, and the token itself.

    Two URLs rather than one because request attributes are read from the classic host over
    Config v1 while DQL runs on the platform host. The same token serves both, sent as
    `Api-Token` to the one and as `Bearer` to the other.
    """

    classic_url: str
    platform_url: str
    platform_token: SecretToken


def derive_url_pair(
    *, tenant: str | None = None, classic: str | None = None, platform: str | None = None
) -> tuple[str, str]:
    """The (classic, platform) pair the inputs name, deriving whichever was not given.

    An unrecognised host is passed through verbatim rather than guessed at, which is also the
    escape hatch when derivation has nothing to go on: give both.
    """
    if classic and platform:
        return _normalised(classic), _normalised(platform)
    if classic:
        return _normalised(classic), _as_platform(_normalised(classic))
    if platform:
        return _as_classic(_normalised(platform)), _normalised(platform)
    if not tenant:
        raise ConfigError(
            "missing tenant URL (provide --tenant, --classic-url or --platform-url, "
            "or set DT_TENANT)"
        )
    named = _normalised(tenant)
    if _is_platform_host(named):
        return _as_classic(named), named
    return named, _as_platform(named)


def _normalised(url: str) -> str:
    return url.rstrip("/")


def _is_platform_host(url: str) -> bool:
    return any(platform in url for _, platform in _HOST_PAIRS)


def _as_platform(classic: str) -> str:
    for classic_infix, platform_infix in _HOST_PAIRS:
        if classic_infix in classic:
            return classic.replace(classic_infix, platform_infix)
    return classic


def _as_classic(platform: str) -> str:
    for classic_infix, platform_infix in _HOST_PAIRS:
        if platform_infix in platform:
            return platform.replace(platform_infix, classic_infix)
    return platform


def build_config(
    *,
    tenant: str | None = None,
    classic_url: str | None = None,
    platform_url: str | None = None,
    env: Mapping[str, str] | None = None,
) -> AppConfig:
    env = os.environ if env is None else env
    classic, platform = derive_url_pair(
        tenant=tenant or env.get("DT_TENANT"),
        classic=classic_url or env.get("DT_CLASSIC_URL"),
        platform=platform_url or env.get("DT_PLATFORM_URL"),
    )
    return AppConfig(
        classic_url=classic,
        platform_url=platform,
        platform_token=SecretToken(_required_token(env)),
    )


def _required_token(env: Mapping[str, str]) -> str:
    token = env.get(_TOKEN_VAR, "").strip()
    if not token:
        raise ConfigError(
            f"missing platform token: set {_TOKEN_VAR} to a {_TOKEN_PREFIX}* token "
            f"with scopes {_TOKEN_SCOPES}"
        )
    if not token.startswith(_TOKEN_PREFIX):
        raise ConfigError(
            f"{_TOKEN_VAR} must hold a platform token starting with {_TOKEN_PREFIX!r}; "
            f"a classic Api-Token ({_CLASSIC_TOKEN_PREFIX}*) is not accepted"
        )
    return token
