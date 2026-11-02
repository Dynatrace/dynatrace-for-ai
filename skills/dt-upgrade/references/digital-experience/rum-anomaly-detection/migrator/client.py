import json
import os
import shutil
import subprocess
import tempfile
import urllib.request


def dtctl_available():
    """Whether dtctl is resolvable on PATH. Callers check this and fail cleanly before

    constructing a DtClient — the client itself never raises for a missing binary, it
    just shells out and lets subprocess fail if this check was skipped.
    """
    return shutil.which("dtctl") is not None


# What the calling token itself needs to run this migrator — reading/writing settings
# objects and schemas, plus the Smartscape lookup for classic-id -> FRONTEND-id mapping.
# This is distinct from the *actor* permissions disclaimer (storage:metrics:read,
# storage:buckets:read, storage:smartscape:read, davis:analyzers:execute), which the
# actor named inside each created object needs at Davis-analyzer-execution-time, not what
# the token creating the object needs. iam:users:read is deliberately excluded: it is
# soft-checked via the 403 fallback in actors.py, not a hard requirement — the migrator
# still works with just the current user if service users can't be listed.
REQUIRED_SCOPES = {
    "settings:objects:read",
    "settings:schemas:read",
    "settings:objects:write",
    "storage:smartscape:read",
}


def missing_required_scopes(client):
    """Required scopes the active context's token does not have, sorted for stable output."""
    return sorted(REQUIRED_SCOPES - client.granted_scopes())


class DtClient:
    """Wraps all external calls to dtctl and the Dynatrace API."""

    DTCTL = "dtctl"

    def get_current_context(self):
        raw = json.loads(subprocess.check_output([self.DTCTL, "ctx", "-o", "json"]).decode())
        contexts = raw["result"] if isinstance(raw, dict) else raw
        current = next(c for c in contexts if c.get("Current") == "*")
        env_url = current["Environment"].rstrip("/")
        env_id = env_url.split("//")[1].split(".")[0]
        return env_url, env_id, current["Name"]

    def get_token(self):
        _, _, ctx_name = self.get_current_context()
        return subprocess.check_output([self.DTCTL, "ctx", "token", ctx_name]).decode().strip()

    def get_settings(self, schema_id):
        raw = subprocess.check_output([self.DTCTL, "get", "settings", "--schema", schema_id, "-o", "json"]).decode()
        return _parse_settings_response(raw)

    def create_settings(self, schema_id, scope, value, validate_only=False):
        """Create one settings object. Returns (ok, message).

        `value` is the settings value only — schema and scope travel as flags.
        """
        handle, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(handle, "w") as f:
                json.dump(value, f)
            cmd = [self.DTCTL, "create", "settings", "-f", path,
                   "--schema", schema_id, "--scope", scope]
            if validate_only:
                cmd.append("--validate-only")
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.returncode == 0, (result.stdout + result.stderr).strip()
        finally:
            os.unlink(path)

    def query(self, dql):
        result = subprocess.check_output([self.DTCTL, "query", dql, "-o", "json", "--plain"]).decode()
        data = json.loads(result)
        if isinstance(data, dict) and "result" in data:
            data = data["result"]
        return data if isinstance(data, list) else data.get("records", [])

    def fetch_url(self, url, token):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req) as resp:
            return resp.read()

    def get_service_users(self, env_url, env_id, token):
        # Platform IAM API — not a classic endpoint. dtctl has no service-user resource at
        # all (`dtctl commands --full` confirms this); its only user-related command, `get
        # users`, is a different, human-search-by-partial-string endpoint, not a listing of
        # service accounts. Verified live: this call and its 403-on-missing-permission
        # fallback (see actors.py) both work as intended.
        url = f"{env_url}/platform/iam/v1/organizational-levels/environment/{env_id}/service-users"
        return json.loads(self.fetch_url(url, token))

    def get_settings_schema(self, schema_id):
        # dtctl's own settings-schema resource — not the classic environment-api schema
        # endpoint. Platform-native, no direct HTTP call or token handling needed.
        raw = subprocess.check_output(
            [self.DTCTL, "get", "settings-schema", schema_id, "-o", "json", "--plain"]).decode()
        data = json.loads(raw)
        return data["result"] if isinstance(data, dict) and "result" in data else data

    def granted_scopes(self):
        """Scopes granted to the active context's token.

        `--check-scopes` reports this identically regardless of which command it's attached
        to — verified live across get/create/query — so one cheap, read-only call (against a
        schema that's certain to exist) is enough to answer "what can this token do at all,"
        without needing a separate check per operation.
        """
        raw = subprocess.check_output([
            self.DTCTL, "get", "settings-schema", "builtin:health-experience.frontend-alert",
            "--check-scopes", "-o", "json", "--plain",
        ]).decode()
        data = json.loads(raw)
        data = data["result"] if isinstance(data, dict) and "result" in data else data
        return set(data.get("granted_scopes", []))


def _parse_settings_response(raw):
    data = json.loads(raw)
    if isinstance(data, dict) and "result" in data:
        data = data["result"]
    return data if isinstance(data, list) else data.get("items", [])
