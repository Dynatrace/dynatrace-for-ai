import base64
import json
import re
import sys
import urllib.error

from client import DtClient, dtctl_available, missing_required_scopes

_MAX_NAME_LEN = 80


def sanitize_display_name(name, max_len=_MAX_NAME_LEN):
    """Neutralize an externally-settable display name before it's ever printed.

    Service user names come from IAM — anyone with permission to manage service users on the
    tenant can set this to arbitrary text, including something that reads as an instruction.
    This script only ever prints plain JSON (see the __main__ block) — no instruction text of
    its own — precisely so a name like this can never land inside a block the agent is told
    to follow literally; that logic lives entirely in the skill doc instead. Still, control
    characters/newlines are stripped and length is capped here, at the one place every name
    passes through, as defense in depth for whatever prints this data downstream.
    """
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", str(name))
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len - 1].rstrip() + "…"
    return cleaned


def fetch_available_actors(client):
    token = client.get_token()
    current_user_id = _decode_sub(token)
    env_url, env_id, _ = client.get_current_context()
    current_user = {"id": current_user_id, "name": "Current user", "type": "user"}
    try:
        data = client.get_service_users(env_url, env_id, token)
        actors = [current_user]
        for u in data.get("results", []):
            name = sanitize_display_name(u.get("name", u["uid"]))
            actors.append({"id": u["uid"], "name": name, "type": "service-user"})
        return actors
    except urllib.error.HTTPError as e:
        print(
            f"Warning: could not fetch service users (HTTP {e.code} — insufficient permissions). "
            f"Only the current user is available.",
            file=sys.stderr,
        )
        return [current_user]


def _decode_sub(token):
    parts = token.split(".")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["sub"]


if __name__ == "__main__":
    if not dtctl_available():
        print("Error: an internal issue prevented this migration from running. "
              "Please try again.", file=sys.stderr)
        sys.exit(1)

    client = DtClient()

    missing = missing_required_scopes(client)
    if missing:
        print("Error: the active token is missing permissions required to run this "
              f"migration: {', '.join(missing)}. Ask whoever manages this environment's "
              "Dynatrace access to grant these, then try again.", file=sys.stderr)
        sys.exit(1)

    # Plain data only, deliberately — no embedded prompting/instruction text here. See
    # rum-anomaly-detection.md's Step 1 for how the agent is supposed to turn this list into
    # question 1. Keeping this script data-only means an untrusted, externally-settable
    # actor `name` (from IAM) can never appear inside a block the agent is told to treat as
    # authoritative instructions — the only place behavioral instructions live is the
    # skill doc itself, which isn't attacker-influenced.
    actors = fetch_available_actors(client)
    print(json.dumps(actors, indent=2))
    print(
        "\nNote: actor permissions are not validated by this script.\n"
        "Ensure the chosen actor has these permissions on the environment:\n"
        "  - storage:metrics:read\n"
        "  - storage:buckets:read\n"
        "  - storage:smartscape:read\n"
        "  - davis:analyzers:execute"
    )
