"""Config v1 ``Api-Token`` header helper."""

from __future__ import annotations


def auth_header(token: str) -> dict[str, str]:
    """Return the ``Authorization`` header for Config v1 REST calls."""

    if not token:
        raise ValueError("api token must be non-empty")
    return {"Authorization": f"Api-Token {token}"}
