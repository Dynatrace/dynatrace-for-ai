from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

# The platform token is accepted from this environment variable and from nowhere else.
_TOKEN_VAR = "DT_PLATFORM_TOKEN"
_TOKEN_PREFIX = "dt0s16."

_TOKEN_SCOPES = "settings:objects:read, storage:spans:read, storage:entities:read"


class ConfigError(ValueError):
    pass


def resolve_platform_url(tenant: str | None) -> str:
    """A platform URL is kept, a classic one converted, and an unrecognised host passed
    through verbatim - which is also the escape hatch when derivation has nothing to go on.
    """
    if not tenant:
        raise ConfigError("missing tenant URL (provide --tenant or set DT_TENANT)")
    norm = _normalise(tenant)
    return norm if ".apps." in norm else _infer_platform(norm)


def _normalise(url: str) -> str:
    return url.rstrip("/")


def _infer_platform(classic: str) -> str:
    return classic.replace(".live.dynatrace.com", ".apps.dynatrace.com")



@dataclass(frozen=True)
class SecretToken:
    """A credential that cannot be printed by accident.

    Masking ``AppConfig.__repr__`` would cover the config object alone, while the token also
    travels into client constructors, log lines and exception text. Wrapping it makes the safe
    rendering the default and forces every real use through :meth:`reveal`.
    """

    _value: str

    def reveal(self) -> str:
        return self._value

    def redact(self, text: str) -> str:
        """Replace any occurrence of the raw value in *text* with the masked form.

        An upstream can put the ``Authorization`` header into a *transport* error message, which
        never passes through :func:`~fdr_migrator.clients.utils.safe_error_hint`. Redaction runs
        before truncation, so a cut cannot leave a usable fragment behind.
        """
        return text.replace(self._value, repr(self)) if self._value else text

    def __repr__(self) -> str:
        prefix, _, _ = self._value.partition(".")
        return f"{prefix}.***" if prefix else "***"

    __str__ = __repr__


@dataclass(frozen=True)
class AppConfig:
    platform_url: str
    platform_token: SecretToken


def build_config(
    *,
    tenant: str | None = None,
    env: Mapping[str, str] | None = None,
) -> AppConfig:
    env = os.environ if env is None else env
    platform = resolve_platform_url(tenant or env.get("DT_TENANT"))
    token = SecretToken(_require_platform_token(env))
    return AppConfig(platform_url=platform, platform_token=token)


def _require_platform_token(env: Mapping[str, str]) -> str:
    token = env.get(_TOKEN_VAR, "").strip()
    if not token:
        raise ConfigError(
            f"missing platform token: set {_TOKEN_VAR} to a {_TOKEN_PREFIX}* token "
            f"with scopes {_TOKEN_SCOPES}"
        )
    if not token.startswith(_TOKEN_PREFIX):
        raise ConfigError(
            f"{_TOKEN_VAR} must hold a platform token starting with {_TOKEN_PREFIX!r}; "
            f"a classic Api-Token (dt0c01.*) is not accepted"
        )
    return token
