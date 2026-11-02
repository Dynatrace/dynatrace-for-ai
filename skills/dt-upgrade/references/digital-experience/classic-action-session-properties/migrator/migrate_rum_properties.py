#!/usr/bin/env python3
"""Migrate classic RUM user-action and session properties to Grail.

Phases, each a subcommand, each separable from the next:

    preflight check the tenant, the credentials and the gates      writes nothing to the tenant
    scan      read classic application configuration           writes nothing to the tenant
    plan      classify, translate, validate, emit artifacts    writes local files only
    apply     write the merged capture-properties objects      writes to the tenant
    verify    re-read what was written                         writes nothing to the tenant
    restore   write a backup artifact back                     writes to the tenant

`plan` is runnable without `apply` ever being reachable in the same invocation: the human
gate lives between them, and `plan`'s artifacts are what the human is shown.

Credentials are never accepted on the command line. They are read from the environment, or
from a `.dtmigration` file that this script parses itself:

    DT_CLASSIC_BASE    environment URL, scheme included, no `.apps` host  (classic config API)
    DT_CLASSIC_TOKEN   classic API token                (scan, and Settings 2.0 for the rest)
    DT_PLATFORM_BASE   platform URL, scheme included, the `.apps` host   (Grail)
    DT_PLATFORM_TOKEN  platform token                     (the queries `verify` emits, Grail)

Which scopes each phase needs is `PHASE_SCOPES` below, and `--help` prints it. In short:
`scan` needs `ReadConfig`; `apply` and `restore` need `settings.read` and `settings.write`;
`verify` needs `settings.read` alone; `plan` needs nothing. Those are scopes on the classic token
-- Environment API v2 does not accept a platform token. The platform token writes the pipeline
and its route in `apply` and `restore` (`settings:objects:read` + `settings:objects:write`), and
runs the queries `verify` emits. Those queries need Grail table scopes *and* an IAM fieldset
policy -- `DQL_SCOPES` and `DQL_FIELDSET_POLICY`.

Stdlib only, Python 3.9+. Run as `python3 migrate_rum_properties.py <command>`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

TOOL_NAME = "migrate_rum_properties"
TOOL_VERSION = "0.1.0"
ARTIFACT_SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_CREDENTIALS = 2
EXIT_PARTIAL = 3
EXIT_API = 4

CONFIG_FILE_NAME = ".dtmigration"
DEFAULT_OUT_DIR = "dt-rum-migration"
DEFAULT_TIMEOUT = 30.0
# A handful of applications is read outright; more than this, and which of them carry
# properties is a question to ask rather than a few minutes of requests to spend.
MAX_AUTO_READ = 10
RETRY_STATUSES = (429, 500, 502, 503, 504)
MAX_ATTEMPTS = 4

# Classic entity IDs, validated before they are ever put into a URL path.
WEB_APP_ID = re.compile(r"^APPLICATION-[0-9A-F]{16}$")
MOBILE_APP_ID = re.compile(r"^(MOBILE_APPLICATION|CUSTOM_APPLICATION)-[0-9A-F]{16}$")

# The documented classic enums. Unknown values are reported, never rejected: this tool
# describes what the tenant returned, it does not police the classic API.
WEB_ORIGINS = frozenset({"JAVASCRIPT_API", "META_DATA", "SERVER_SIDE_REQUEST_ATTRIBUTE"})
MOBILE_ORIGINS = frozenset({"API", "SERVER_SIDE_REQUEST_ATTRIBUTE"})
WEB_TYPES = frozenset({"DATE", "DOUBLE", "LONG", "LONG_STRING", "STRING"})
MOBILE_TYPES = frozenset({"DOUBLE", "LONG", "STRING"})
WEB_AGGREGATIONS = frozenset({"AVERAGE", "FIRST", "LAST", "MAXIMUM", "MINIMUM", "SUM"})
MOBILE_AGGREGATIONS = frozenset({"AVERAGE", "FIRST", "LAST", "MAX", "MIN", "SUM"})
CAPTURE_TYPES = frozenset(
    {
        "COOKIE",
        "CSS_SELECTOR",
        "JAVA_SCRIPT_FUNCTION",
        "JAVA_SCRIPT_VARIABLE",
        "META_TAG",
        "QUERY_STRING",
        "RESPONSE_HEADER",
    }
)

# Anything token-shaped is stripped from a message before it is printed or written to an
# artifact. The API echoes request context in some errors, and one of those echoes is enough
# to leak a credential into a log that is later pasted somewhere else.
TOKEN_SHAPE = re.compile(r"dt0[a-z]\d{2}\.[A-Za-z0-9]{4,}(?:\.[A-Za-z0-9]{4,})?")


# --------------------------------------------------------------------------- errors


class MigratorError(Exception):
    """Base for every error this tool raises deliberately.

    `fix` is what the reader can do about it: concrete commands, flags or settings, each one an
    alternative. A refusal that only says no leaves an agent guessing, and a guess at the edge of
    a refusal is how a migration gets worked around rather than through.
    """

    exit_code = EXIT_API

    def __init__(self, message: str, *, fix: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.fix: List[str] = list(fix or [])

    @property
    def what_to_do(self) -> List[str]:
        return self.fix


class UsageError(MigratorError):
    exit_code = EXIT_USAGE


class CredentialError(MigratorError):
    exit_code = EXIT_CREDENTIALS


class ApiError(MigratorError):
    """An HTTP call failed. Carries the API's own message, which is more specific than ours."""

    exit_code = EXIT_API

    def __init__(
        self, status: int, message: str, url_path: str = "", *, fix: Optional[List[str]] = None
    ) -> None:
        super().__init__(message, fix=fix)
        self.status = status
        self.message = message
        self.url_path = url_path

    @property
    def what_to_do(self) -> List[str]:
        return self.fix or api_remedy(self.status)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "path": self.url_path,
            "whatToDo": self.what_to_do,
        }


def api_remedy(status: int) -> List[str]:
    """What to do about a status the API answered with, when the call site knows nothing better."""
    if status == 401:
        return [
            "The token was refused. Check that the token for that host is set, current and not "
            "expired -- DT_CLASSIC_TOKEN on the classic host, DT_PLATFORM_TOKEN on the `.apps` "
            "host -- then re-run the same command."
        ]
    if status == 403:
        return [
            "The token is missing a scope; the message names it when the API does. "
            "`<command> --help` lists every scope a command needs. Use a token that carries "
            "them and re-run the same command."
        ]
    if status == 404:
        return [
            "Check that the host names the right tenant -- the classic APIs answer 404 on the "
            "`.apps` host and the platform ones on the classic host -- and that the id exists "
            "there: `scan --all` lists the applications."
        ]
    if status == 400:
        return [
            "The tenant refused the request as invalid, and the message names what. Correct the "
            "input it names and re-run the same command; if the input came unchanged from "
            "`plan`, report the command and the message."
        ]
    if status in (409, 412):
        return ["The object changed while this ran. Re-run the same command: it reads afresh."]
    if status == 429 or status >= 500:
        return ["The tenant is busy or failing. Wait a minute and re-run the same command."]
    return ["Re-run the same command. If it fails the same way, report the command and the message."]


def set_fix(name: str, example: str) -> List[str]:
    """How to give this tool a setting -- the one remedy every missing setting shares."""
    return [
        f"Set {name} to {example}, exported before this session starts or as a `{name}=...` line "
        f"in {CONFIG_FILE_NAME} in the working directory (or a file named with --config), then "
        "re-run the same command."
    ]


CLASSIC_EXAMPLE = "https://<environment>.live.dynatrace.com"
PLATFORM_EXAMPLE = "https://<environment>.apps.dynatrace.com"
FIX_OUT_DIR = ["Pass --out-dir DIR naming the directory explicitly, e.g. --out-dir dt-rum-migration."]
FIX_UNEXPECTED = [
    "Check that the host setting names a Dynatrace environment, then re-run the same command. If "
    "it fails the same way, report the command and the message: the API answered in a shape this "
    "tool does not know."
]
FIX_NOT_JSON = [
    "Check that the host setting names a Dynatrace environment and not a login page or a proxy "
    "(open it in a browser), then re-run the same command."
]
FIX_CONNECTION = [
    "Check that the host in DT_CLASSIC_BASE or DT_PLATFORM_BASE is spelled right and reachable "
    "from this machine (proxy, VPN), then re-run the same command."
]
FIX_FOREIGN_BACKUP = [
    "Point --backup at a backup-<stamp>.json or pre-restore-<stamp>.json this tool wrote, "
    "unedited -- or leave --backup out to use the newest backup in --out-dir."
]


def redact(text: str) -> str:
    return TOKEN_SHAPE.sub("dt0…", text)


# --------------------------------------------------------------------------- credentials


def parse_config_file(text: str) -> Dict[str, str]:
    """Parse a `.dtmigration` file: KEY=VALUE lines, `#` comments, optional `export` and quotes."""
    values: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


SETTING_NAMES = ("DT_CLASSIC_BASE", "DT_CLASSIC_TOKEN", "DT_PLATFORM_BASE", "DT_PLATFORM_TOKEN")

# Appended to every "is not set" error. The likeliest cause in an agent session is not a missing
# variable but one exported in another shell after the agent started, which it can never see.
NOT_SET_HINT = (
    f"A variable exported after this session started is invisible to it: export it before "
    f"starting, or put it in a {CONFIG_FILE_NAME} file in the working directory (or name one "
    "with --config) -- KEY=VALUE lines, read by this tool and never printed."
)


def settings_sources(
    env: Optional[Dict[str, str]] = None,
    config_path: Optional[Path] = None,
) -> Dict[str, str]:
    """Where each documented setting comes from: `environment`, the config file, or `unset`.

    Names and origins only. It is what `preflight` reports, so that "which tenant is this" is
    answered by the tool rather than inferred from some other tool's context.
    """
    env = dict(os.environ if env is None else env)
    path = config_path if config_path is not None else Path.cwd() / CONFIG_FILE_NAME
    from_file = parse_config_file(path.read_text(encoding="utf-8")) if path.is_file() else {}
    sources: Dict[str, str] = {}
    for name in SETTING_NAMES:
        if env.get(name):
            sources[name] = "environment"
        elif from_file.get(name):
            sources[name] = str(path.resolve())
        else:
            sources[name] = "unset"
    return sources


def load_settings(
    env: Optional[Dict[str, str]] = None,
    config_path: Optional[Path] = None,
) -> Dict[str, str]:
    """Environment first, `.dtmigration` as the documented fallback.

    Only the four documented names are read. The environment is never iterated looking for
    anything token-shaped.
    """
    env = dict(os.environ if env is None else env)
    resolved = {name: env[name] for name in SETTING_NAMES if env.get(name)}

    path = config_path if config_path is not None else Path.cwd() / CONFIG_FILE_NAME
    if path.is_file():
        from_file = parse_config_file(path.read_text(encoding="utf-8"))
        for name in SETTING_NAMES:
            if name not in resolved and from_file.get(name):
                resolved[name] = from_file[name]
    return resolved


def classic_host(settings: Dict[str, str]) -> str:
    """The tenant this run talks to, as every artifact records it."""
    base = settings.get("DT_CLASSIC_BASE")
    if not base:
        raise CredentialError(
            f"DT_CLASSIC_BASE is not set. {NOT_SET_HINT}",
            fix=set_fix("DT_CLASSIC_BASE", CLASSIC_EXAMPLE),
        )
    return urllib.parse.urlsplit(
        normalise_base(base, expect_apps_host=False, label="DT_CLASSIC_BASE")
    ).netloc


def normalise_base(value: str, *, expect_apps_host: bool, label: str) -> str:
    """Validate an environment URL and return it without a trailing slash.

    The two hosts are different machines with different auth schemes, and swapping them
    produces a 404 that reads like a missing feature. Catch it here instead.
    """
    value = value.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    example = PLATFORM_EXAMPLE if expect_apps_host else CLASSIC_EXAMPLE
    if parsed.scheme != "https" or not parsed.netloc:
        raise UsageError(
            f"{label} must be a full environment URL including the https scheme, "
            f"for example: {example}",
            fix=set_fix(label, example),
        )
    is_apps_host = ".apps." in parsed.netloc
    if expect_apps_host and not is_apps_host:
        raise UsageError(
            f"{label} looks like the classic host. The platform APIs live on the `.apps` host; "
            f"the classic configuration API does not.",
            fix=set_fix(label, example),
        )
    if not expect_apps_host and is_apps_host:
        raise UsageError(
            f"{label} looks like the platform host. The classic configuration API is only "
            f"served by the environment host without `.apps`, and returns 404 on the other one.",
            fix=set_fix(label, example),
        )
    return value


# --------------------------------------------------------------------------- http


class HttpClient:
    """Minimal JSON client over urllib, with retry on the statuses that mean 'try again'."""

    def __init__(
        self,
        base: str,
        auth_header: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        max_attempts: int = MAX_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base = base.rstrip("/")
        self._auth_header = auth_header
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._sleep = sleep

    def get_json(self, path: str, params: Optional[Dict[str, str]] = None) -> Any:
        body = self._get(path, params, accept="application/json")
        try:
            return json.loads(body) if body else None
        except json.JSONDecodeError as exc:
            raise ApiError(0, f"response was not JSON: {exc}", path, fix=FIX_NOT_JSON)

    def get_text(self, path: str, params: Optional[Dict[str, str]] = None) -> str:
        """For the one endpoint that answers `text/plain`: the agent tag `preflight` reads."""
        return self._get(path, params, accept="text/plain")

    def _get(self, path: str, params: Optional[Dict[str, str]], *, accept: str) -> str:
        url = self._base + path
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, method="GET")
        request.add_header("Authorization", self._auth_header)
        request.add_header("Accept", accept)
        request.add_header("User-Agent", f"{TOOL_NAME}/{TOOL_VERSION}")

        last_error: Optional[ApiError] = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                detail = _http_error_message(exc)
                last_error = ApiError(exc.code, detail, path)
                if exc.code in RETRY_STATUSES and attempt < self._max_attempts:
                    self._sleep(_retry_delay(exc, attempt))
                    continue
                raise last_error
            except urllib.error.URLError as exc:
                last_error = ApiError(
                    0, f"connection failed: {redact(str(exc.reason))}", path, fix=FIX_CONNECTION
                )
                if attempt < self._max_attempts:
                    self._sleep(float(2 ** (attempt - 1)))
                    continue
                raise last_error
        raise last_error or ApiError(0, "request failed", path)

    def send_json(
        self,
        method: str,
        path: str,
        payload: Any,
        params: Optional[Dict[str, str]] = None,
    ) -> Any:
        """POST or PUT, retried on **429 only**.

        A read can be retried on anything that might be transient because repeating it changes
        nothing. A write cannot: a `502` or a dropped connection on a `POST` can mean the object
        was created and the response was lost, and retrying that creates a second one or repeats
        an overwrite. `429` is the one status where the API has told us it did *not* process the
        request, so it is the one status this retries.
        """
        url = self._base + path
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        body = json.dumps(payload).encode("utf-8")

        last_error: Optional[ApiError] = None
        for attempt in range(1, self._max_attempts + 1):
            request = urllib.request.Request(url, data=body, method=method)
            request.add_header("Authorization", self._auth_header)
            request.add_header("Accept", "application/json")
            request.add_header("Content-Type", "application/json")
            request.add_header("User-Agent", f"{TOOL_NAME}/{TOOL_VERSION}")
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    text = response.read().decode("utf-8")
                return json.loads(text) if text else None
            except urllib.error.HTTPError as exc:
                last_error = ApiError(exc.code, _http_error_message(exc), path)
                if exc.code == 429 and attempt < self._max_attempts:
                    self._sleep(_retry_delay(exc, attempt))
                    continue
                raise last_error
            except urllib.error.URLError as exc:
                raise ApiError(
                    0, f"connection failed: {redact(str(exc.reason))}", path, fix=FIX_CONNECTION
                )
            except json.JSONDecodeError as exc:
                raise ApiError(0, f"response was not JSON: {exc}", path, fix=FIX_NOT_JSON)
        raise last_error or ApiError(0, "request failed", path)

    def delete(self, path: str, params: Optional[Dict[str, str]] = None) -> None:
        """DELETE, retried on **429 only**, and treating `404` as success.

        Same rule as the other writes: `429` is the one status that says the request was not
        processed. `404` is the exception a delete can afford -- the object is gone, which is
        what was asked for, and a run that has already deleted it should not fail the second
        time it is asked to.
        """
        url = self._base + path
        if params:
            url = url + "?" + urllib.parse.urlencode(params)

        last_error: Optional[ApiError] = None
        for attempt in range(1, self._max_attempts + 1):
            request = urllib.request.Request(url, method="DELETE")
            request.add_header("Authorization", self._auth_header)
            request.add_header("Accept", "application/json")
            request.add_header("User-Agent", f"{TOOL_NAME}/{TOOL_VERSION}")
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    response.read()
                return None
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return None
                last_error = ApiError(exc.code, _http_error_message(exc), path)
                if exc.code == 429 and attempt < self._max_attempts:
                    self._sleep(_retry_delay(exc, attempt))
                    continue
                raise last_error
            except urllib.error.URLError as exc:
                raise ApiError(
                    0, f"connection failed: {redact(str(exc.reason))}", path, fix=FIX_CONNECTION
                )
        raise last_error or ApiError(0, "request failed", path)


def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header:
        try:
            return min(float(header), 60.0)
        except ValueError:
            pass
    return float(2 ** (attempt - 1))


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    """Surface the API's own message. It is consistently more specific than a paraphrase."""
    try:
        body = exc.read().decode("utf-8")
    except Exception:  # noqa: BLE001 - the error body is best-effort by definition
        body = ""
    message = ""
    if body:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            message = body.strip()
        else:
            if isinstance(parsed, dict):
                error = parsed.get("error")
                if isinstance(error, dict):
                    message = str(error.get("message") or "")
                    details = error.get("details")
                    if isinstance(details, dict) and details.get("errorMessage"):
                        message = f"{message}: {details['errorMessage']}".strip(": ")
                    scopes = details.get("missingScopes") if isinstance(details, dict) else None
                    if isinstance(scopes, list) and scopes:
                        message = f"{message} (missing scopes: {', '.join(map(str, scopes))})"
                    violations = error.get("constraintViolations")
                    if isinstance(violations, list) and violations:
                        parts = [
                            str(v.get("message"))
                            for v in violations
                            if isinstance(v, dict) and v.get("message")
                        ]
                        if parts:
                            message = f"{message} ({'; '.join(parts)})".strip()
                elif isinstance(error, str):
                    message = error
            if not message:
                message = body.strip()
    if not message:
        message = exc.reason or "request failed"
    return redact(" ".join(message.split()))[:1000]


# ------------------------------------------------------------------- required scopes
# What each phase needs, and nothing beyond it. Worth reading before the first run rather
# than after the first 403: a platform token's scopes are fixed when it is created, so a
# token minted one scope short has to be replaced, not amended.
#
# Two credentials, and which one goes where is measured rather than assumed. The classic API
# token reaches `/api/config/v1/...` (the application configuration `scan` reads) and Environment
# API v2 (Settings 2.0, where `apply` writes). The platform token reaches Grail, and Grail only:
# Environment API v2 answers a platform token with `401 Token exchange failed`, so the settings
# phases take the classic token.
#
# The pipeline and its route are platform objects, written by `apply` and undone by `restore`
# with the platform token -- the one place a platform scope is a phase's own.
PLATFORM_SCOPES = ("settings:objects:read", "settings:objects:write")

# The scopes below are per phase, and nothing requires one token to serve them all. A run that
# only applies needs the settings scopes and not `ReadConfig`; a token that only scans needs
# `ReadConfig` and cannot write anything at all.
PHASE_SCOPES: Dict[str, Dict[str, Any]] = {
    "preflight": {
        "summary": "DT_CLASSIC_TOKEN with ReadConfig + settings.read (+ settings.write, checked)",
        "classic": ("ReadConfig", "settings.read", "settings.write"),
        "platform": (),
        "note": (
            "Nothing is written. settings.write is checked with a validate-only request, which "
            "the tenant evaluates and discards, so a token without it is reported rather than "
            "refused. DT_PLATFORM_TOKEN, when set, is checked with one read."
        ),
    },
    "scan": {
        "summary": "DT_CLASSIC_TOKEN with ReadConfig",
        "classic": ("ReadConfig",),
        "platform": (),
        "note": "WriteConfig is not needed: scan reads and never writes.",
    },
    "plan": {
        "summary": "none -- plan contacts no tenant",
        "classic": (),
        "platform": (),
        "note": "It reads the scan artifact and writes local files.",
    },
    "apply": {
        "summary": "DT_CLASSIC_TOKEN with settings.read + settings.write; DT_PLATFORM_TOKEN "
        "with settings:objects:read + settings:objects:write",
        "classic": ("settings.read", "settings.write"),
        "platform": PLATFORM_SCOPES,
        "note": (
            "Creating an object reads the schema list for its version, which `settings.read` "
            "covers. `scan`'s ReadConfig is not needed here: a token that only applies can be "
            "narrower than one that also scans. The platform token writes the pipeline and its "
            "route; --capture-only skips that half and needs no platform token."
        ),
    },
    "verify": {
        "summary": "DT_CLASSIC_TOKEN with settings.read",
        "classic": ("settings.read",),
        "platform": (),
        "note": (
            "Read-only on purpose. A phase that checks a write should not need permission to "
            "repeat it, so the token that verifies can be narrower than the one that applied."
        ),
    },
    "restore": {
        "summary": "DT_CLASSIC_TOKEN with settings.read + settings.write; DT_PLATFORM_TOKEN "
        "with settings:objects:read + settings:objects:write",
        "classic": ("settings.read", "settings.write"),
        "platform": PLATFORM_SCOPES,
        "note": "Undoing a run writes, and an object the run created is deleted rather than "
        "emptied. The platform token is needed only when the backup has a pipeline section.",
    },
}

# The queries `verify` emits are run by you, in a notebook or against the query API, and they
# are the only part of this that touches Grail. Each name here has to be **both** a scope on the
# token and a permission granted to the user that token belongs to: the token is the narrower of
# the two, never the wider, and a refusal names the scope either way.
DQL_SCOPES = (
    "storage:buckets:read",
    "storage:user.events:read",
    "storage:user.sessions:read",
    # Only the session queries need this one, and they cannot do without it: the session table
    # names an application by a frontend id, and nothing derives that id from the id you
    # configure with. Without the scope those queries return no rows rather than an error.
    "storage:smartscape:read",
)
# Not a token scope, and the reason an authorised query can still come back empty: the RUM
# fields these queries read are behind a fieldset, granted by an IAM policy rather than by the
# token. Without it there is no error -- the fields are simply null.
DQL_FIELDSET_POLICY = (
    'ALLOW storage:fieldsets:read WHERE storage:fieldset-name = '
    '"builtin-sensitive-user-events-and-sessions"'
)


def scopes_epilogue() -> str:
    """The whole permission story as one block, for `--help`."""
    lines = ["what each phase needs:", ""]
    for phase, entry in PHASE_SCOPES.items():
        lines.append(f"  {phase:<8} {entry['summary']}")
    lines += [
        "",
        "  The queries `verify` emits, when you run them, need a platform token with",
        "  " + ", ".join(DQL_SCOPES) + ",",
        "  and your user needs the fieldset policy",
        "  " + DQL_FIELDSET_POLICY + ".",
        "  The policy is granted to a group, not minted into a token. Without it the RUM",
        "  fields read as null and a filtered query finds nothing, with no error.",
    ]
    return "\n".join(lines)


def classic_client(settings: Dict[str, str], *, timeout: float = DEFAULT_TIMEOUT) -> HttpClient:
    base = settings.get("DT_CLASSIC_BASE")
    token = settings.get("DT_CLASSIC_TOKEN")
    if not base:
        raise CredentialError(
            f"DT_CLASSIC_BASE is not set. {NOT_SET_HINT}",
            fix=set_fix("DT_CLASSIC_BASE", CLASSIC_EXAMPLE),
        )
    if not token:
        raise CredentialError(
            "DT_CLASSIC_TOKEN is not set. `scan` needs a classic API token with the ReadConfig "
            "scope. On a tenant that has already been upgraded a new classic token can no "
            f"longer be created, so use one you already hold. {NOT_SET_HINT}",
            fix=set_fix("DT_CLASSIC_TOKEN", "a classic API token with ReadConfig"),
        )
    return HttpClient(
        normalise_base(base, expect_apps_host=False, label="DT_CLASSIC_BASE"),
        f"Api-Token {token}",
        timeout=timeout,
    )


def settings_client(
    settings: Dict[str, str], *, timeout: float = DEFAULT_TIMEOUT, phase: str = "apply"
) -> Tuple[HttpClient, str]:
    """A client for Settings 2.0, and the *name* of the variable whose token it used.

    Settings 2.0 is Environment API v2, served by the environment host -- the one without
    `.apps` -- and reached with a classic API token.

    A platform token is not a substitute here, and this is worth stating because the two hosts
    invite the assumption that it is. Sent to Environment API v2 it answers `401 Token exchange
    failed`: the request never reaches the point of being authorized, so no choice of scopes at
    minting time changes the outcome. The platform token's job in this tool is the pipeline half
    of `apply` and `restore`, and the verification queries.

    The scopes are per phase. If you would rather the token that reads every application's
    configuration not also be able to change it, run `scan` with a `ReadConfig` token and the
    settings phases with a `settings.read` (+ `settings.write`) one -- nothing here requires
    them to be the same token.
    """
    base = settings.get("DT_CLASSIC_BASE")
    if not base:
        raise CredentialError(
            "DT_CLASSIC_BASE is not set. Settings 2.0 is served by the environment host without "
            f"`.apps`, so this phase needs that URL. {NOT_SET_HINT}",
            fix=set_fix("DT_CLASSIC_BASE", CLASSIC_EXAMPLE),
        )
    classic_token = settings.get("DT_CLASSIC_TOKEN")
    if not classic_token:
        entry = PHASE_SCOPES.get(phase, PHASE_SCOPES["apply"])
        classic = ", ".join(f"`{name}`" for name in entry["classic"])
        extra = ""
        if settings.get("DT_PLATFORM_TOKEN"):
            extra = (
                " DT_PLATFORM_TOKEN is set and cannot stand in for it: Environment API v2 "
                "answers a platform token with `401 Token exchange failed`, whatever scopes it "
                "carries. The platform token is for the pipeline and the verification "
                "queries."
            )
        raise CredentialError(
            f"DT_CLASSIC_TOKEN is not set. `{phase}` needs one with {classic}. "
            f"{entry['note']}{extra} {NOT_SET_HINT}",
            fix=set_fix("DT_CLASSIC_TOKEN", f"a classic API token with {classic}"),
        )
    return (
        HttpClient(
            normalise_base(base, expect_apps_host=False, label="DT_CLASSIC_BASE"),
            f"Api-Token {classic_token}",
            timeout=timeout,
        ),
        "DT_CLASSIC_TOKEN",
    )


# --------------------------------------------------------------------------- scan


def progress_to_stderr(message: str) -> None:
    """Progress goes to stderr so stdout stays a single machine-readable document."""
    print(message, file=sys.stderr, flush=True)


class ScanResult:
    def __init__(self) -> None:
        self.applications: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []


def list_applications(client: HttpClient, kind: str) -> List[Dict[str, Any]]:
    """Enumerate classic applications. `values` is the wire shape for both kinds."""
    payload = client.get_json(f"/api/config/v1/applications/{kind}")
    if not isinstance(payload, dict):
        raise ApiError(
            0, f"unexpected response listing {kind} applications", "", fix=FIX_UNEXPECTED
        )
    values = payload.get("values")
    if not isinstance(values, list):
        return []
    return [v for v in values if isinstance(v, dict) and v.get("id")]


def read_application(client: HttpClient, kind: str, app_id: str) -> Dict[str, Any]:
    quoted = urllib.parse.quote(app_id, safe="")
    payload = client.get_json(f"/api/config/v1/applications/{kind}/{quoted}")
    if not isinstance(payload, dict):
        raise ApiError(
            0, "unexpected application response", f"/applications/{kind}/{app_id}",
            fix=FIX_UNEXPECTED,
        )
    return payload


def _mobile_summary_entries(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """The mobile collection's shape, measured: two lists of summaries, split by scope.

    `{"sessionProperties": [...], "userActionProperties": [...]}`, each entry carrying `key` and
    `displayName` and nothing else. A key present in both lists is one property
    with both scope flags set, so entries are de-duplicated by key. A flat list is accepted too --
    tolerating it costs nothing.
    """
    if isinstance(payload, list):
        return [entry for entry in payload if isinstance(entry, dict)]
    if not isinstance(payload, dict):
        return None
    if "userActionProperties" in payload or "sessionProperties" in payload:
        merged: List[Dict[str, Any]] = []
        seen: set = set()
        for list_name in ("userActionProperties", "sessionProperties"):
            for entry in payload.get(list_name) or []:
                if not isinstance(entry, dict):
                    continue
                key = str(entry.get("key"))
                if key in seen:
                    continue
                seen.add(key)
                merged.append(entry)
        return merged
    for key in ("values", "properties", "userActionAndSessionProperties"):
        value = payload.get(key)
        if isinstance(value, list):
            return [entry for entry in value if isinstance(entry, dict)]
    return None


def read_mobile_properties_subresource(
    client: HttpClient, app_id: str, result: ScanResult
) -> Optional[List[Dict[str, Any]]]:
    """Read a mobile application's properties: the collection, then one GET per property.

    Mobile keeps its properties **only** here -- the application object never carries them, and a
    create that includes them inline is answered `201` with nothing stored. The
    collection lists summaries, so every definition costs its own request: a mobile application is
    1 + N requests, not one.

    `None` means the route is absent (`404`). An empty list means the route answered and the
    application has no properties -- a distinction the earlier build collapsed, reporting a shape
    it could not parse as though nothing was configured.
    """
    quoted = urllib.parse.quote(app_id, safe="")
    base = f"/api/config/v1/applications/mobile/{quoted}/userActionAndSessionProperties"
    try:
        payload = client.get_json(base)
    except ApiError as exc:
        if exc.status == 404:
            return None
        result.warnings.append(
            {
                "applicationId": app_id,
                "kind": "subresource-unreadable",
                "detail": f"HTTP {exc.status}: {exc.message}",
            }
        )
        return None

    entries = _mobile_summary_entries(payload)
    if entries is None:
        result.warnings.append(
            {
                "applicationId": app_id,
                "kind": "unknown-subresource-shape",
                "detail": "the mobile properties sub-resource answered with a shape this build "
                "does not parse; expected sessionProperties/userActionProperties lists",
            }
        )
        return None

    properties: List[Dict[str, Any]] = []
    for entry in entries:
        # A flat-list entry already is a definition; a summary is not, and has to be fetched.
        if entry.get("origin") or entry.get("type"):
            properties.append(entry)
            continue
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            result.warnings.append(
                {
                    "applicationId": app_id,
                    "kind": "property-without-key",
                    "detail": "a mobile property summary carried no key and cannot be read",
                }
            )
            continue
        try:
            definition = client.get_json(f"{base}/{urllib.parse.quote(key, safe='')}")
        except ApiError as exc:
            result.warnings.append(
                {
                    "applicationId": app_id,
                    "kind": "property-definition-unreadable",
                    "detail": f"HTTP {exc.status}: {exc.message}",
                }
            )
            properties.append(entry)
            continue
        if isinstance(definition, dict):
            properties.append(definition)
        else:
            result.warnings.append(
                {
                    "applicationId": app_id,
                    "kind": "property-definition-unreadable",
                    "detail": "the property definition was not an object",
                }
            )
            properties.append(entry)
    return properties


def _enum_warnings(kind: str, app_id: str, properties: Iterable[Any]) -> List[Dict[str, Any]]:
    """Report every classic value we do not recognise. Reporting, not rejecting."""
    origins = WEB_ORIGINS if kind == "web" else MOBILE_ORIGINS
    types = WEB_TYPES if kind == "web" else MOBILE_TYPES
    aggregations = WEB_AGGREGATIONS if kind == "web" else MOBILE_AGGREGATIONS
    warnings: List[Dict[str, Any]] = []
    for index, prop in enumerate(properties):
        if not isinstance(prop, dict):
            warnings.append(
                {
                    "applicationId": app_id,
                    "kind": "unexpected-property-shape",
                    "detail": f"property at index {index} is not an object",
                }
            )
            continue
        for field, allowed in (
            ("origin", origins),
            ("type", types),
            ("aggregation", aggregations),
        ):
            value = prop.get(field)
            if value is not None and value not in allowed:
                warnings.append(
                    {
                        "applicationId": app_id,
                        "kind": "unknown-enum-value",
                        "detail": f"{field}={value!r} is not a documented classic {kind} value",
                    }
                )
        if not prop.get("key"):
            warnings.append(
                {
                    "applicationId": app_id,
                    "kind": "missing-key",
                    "detail": f"property at index {index} has no `key`",
                }
            )
    return warnings


def _capture_warnings(app_id: str, settings: Iterable[Any]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    for index, item in enumerate(settings):
        if not isinstance(item, dict):
            continue
        capture_type = item.get("type")
        if capture_type is not None and capture_type not in CAPTURE_TYPES:
            warnings.append(
                {
                    "applicationId": app_id,
                    "kind": "unknown-enum-value",
                    "detail": f"metaDataCaptureSettings[{index}].type={capture_type!r} "
                    "is not a documented classic value",
                }
            )
    return warnings


def _user_tag_warnings(app_id: str, tags: Iterable[Any]) -> List[Dict[str, Any]]:
    """What the tenant returned that the translation cannot account for.

    A tag that names neither a capture setting nor a request attribute is the shape worth
    warning about: it is not a tag this tool blocks with a reason, it is a tag whose source is
    unknown, and a scan that passed over it silently would under-report the application.
    """
    warnings: List[Dict[str, Any]] = []
    for index, item in enumerate(tags):
        if not isinstance(item, dict):
            warnings.append(
                {
                    "applicationId": app_id,
                    "kind": "unexpected-user-tag-shape",
                    "detail": f"userTags[{index}] is not an object",
                }
            )
            continue
        if item.get("metadataId") is None and item.get("serverSideRequestAttribute") is None:
            warnings.append(
                {
                    "applicationId": app_id,
                    "kind": "user-tag-without-source",
                    "detail": f"userTags[{index}] names neither a metadataId nor a "
                    "serverSideRequestAttribute, so there is nothing for it to read",
                }
            )
    return warnings


def scan_application(
    client: HttpClient, kind: str, entry: Dict[str, Any], result: ScanResult
) -> None:
    app_id = str(entry.get("id"))
    pattern = WEB_APP_ID if kind == "web" else MOBILE_APP_ID
    if not pattern.match(app_id):
        result.errors.append(
            {
                "applicationId": app_id,
                "kind": kind,
                "stage": "identify",
                "status": 0,
                "message": "application id is not a classic entity id of the expected form",
            }
        )
        return

    try:
        config = read_application(client, kind, app_id)
    except ApiError as exc:
        result.errors.append(
            {
                "applicationId": app_id,
                "kind": kind,
                "stage": "read",
                "status": exc.status,
                "message": exc.message,
                "whatToDo": exc.what_to_do,
            }
        )
        return

    # Absent is not empty, and absent is the common case: an application that never configured
    # a property has no `userActionAndSessionProperties` key at all.
    properties_present = "userActionAndSessionProperties" in config
    properties = config.get("userActionAndSessionProperties")
    properties_source = "application" if properties_present else "absent"
    if not isinstance(properties, list):
        properties = []

    if kind == "mobile" and not properties_present:
        from_subresource = read_mobile_properties_subresource(client, app_id, result)
        if from_subresource is not None:
            # An empty list here is not the web "absent" case: the route answered, and the
            # answer was that this application has no properties.
            properties = from_subresource
            properties_present = True
            properties_source = "subresource"

    capture_present = "metaDataCaptureSettings" in config
    capture_settings = config.get("metaDataCaptureSettings")
    if not isinstance(capture_settings, list):
        capture_settings = []

    # Same absent-is-not-empty rule as the properties above, and it matters more here: an
    # application with `userTags: []` has had its tagging removed, while one with no key at all
    # never had any. `apply` writes user tagging through a different object entirely, so the
    # difference never reaches a write -- but it is the difference between "migrated nothing"
    # and "there was nothing", and the report says which.
    user_tags_present = "userTags" in config
    user_tags = config.get("userTags")
    if not isinstance(user_tags, list):
        user_tags = []

    result.warnings.extend(_enum_warnings(kind, app_id, properties))
    result.warnings.extend(_capture_warnings(app_id, capture_settings))
    result.warnings.extend(_user_tag_warnings(app_id, user_tags))
    if kind == "mobile" and capture_present and capture_settings:
        result.warnings.append(
            {
                "applicationId": app_id,
                "kind": "unexpected-mobile-shape",
                "detail": "mobile application returned metaDataCaptureSettings; mobile has no "
                "configuration capture and the Grail mobile schema has no capturing steps",
            }
        )

    result.applications.append(
        {
            "id": app_id,
            "kind": kind,
            "entityType": app_id.split("-", 1)[0],
            "name": config.get("name") or entry.get("name"),
            "userActionAndSessionPropertiesPresent": properties_present,
            "userActionAndSessionPropertiesSource": properties_source,
            "userActionAndSessionProperties": properties,
            "metaDataCaptureSettingsPresent": capture_present,
            "metaDataCaptureSettings": capture_settings,
            "userTagsPresent": user_tags_present,
            # ⚠ Array order is semantic -- the first matching tag wins inside a user action --
            # so this list is stored exactly as the tenant returned it and must never be sorted.
            "userTags": user_tags,
            "raw": config,
        }
    )


def kind_for_id(app_id: str) -> Optional[str]:
    """A classic entity id carries its own kind, so a named application needs no enumeration."""
    if WEB_APP_ID.match(app_id):
        return "web"
    if MOBILE_APP_ID.match(app_id):
        return "mobile"
    return None


def resolve_applications(
    client: HttpClient, values: Optional[List[str]], kinds: Tuple[str, ...] = ("web", "mobile")
) -> Tuple[List[str], Dict[str, str]]:
    """`--application` as the user knows it: an entity id, or the application's name.

    A name resolves only when exactly one application carries it. Anything else is refused with
    the candidates, because a guess picks the tenant's other "Shop" and migrates that one.
    Returns the ids, in the order given, and the names that were resolved to them.
    """
    ids: List[str] = []
    resolved: Dict[str, str] = {}
    listed: Optional[List[Dict[str, Any]]] = None
    for value in (value.strip() for value in values or []):
        if kind_for_id(value):
            ids.append(value)
            continue
        if listed is None:
            listed = [app for kind in kinds for app in list_applications(client, kind)]
        matches = [app for app in listed if app.get("name") == value]
        if len(matches) == 1:
            ids.append(matches[0]["id"])
            resolved[value] = matches[0]["id"]
            continue
        if matches:
            raise UsageError(
                f"{len(matches)} applications are named {value!r}. Nothing was read.",
                fix=["Ask the user which one, and pass its id with --application:"]
                + [f"{app['id']} ({app['name']})" for app in matches],
            )
        similar = [app for app in listed if value.lower() in str(app.get("name") or "").lower()]
        raise UsageError(
            f"No application is named {value!r} exactly. Nothing was read.",
            fix=(["Ask the user which one is meant, and pass its id or exact name with "
                  "--application:"]
                 + [f"{app['id']} ({app['name']})" for app in similar[:10]])
            if similar else
            ["Run `scan` without --application to list every application, and ask the user "
             "which one is meant."],
        )
    return ids, resolved


def _list_error(kind: str, exc: ApiError) -> Dict[str, Any]:
    return {
        "applicationId": None,
        "kind": kind,
        "stage": "list",
        "status": exc.status,
        "message": exc.message,
        "whatToDo": exc.what_to_do,
    }


class InventoryResult:
    def __init__(self) -> None:
        self.entries: List[Dict[str, Any]] = []
        self.errors: List[Dict[str, Any]] = []
        self.request_seconds: float = 0.0
        self.request_count: int = 0

    def seconds_per_request(self) -> Optional[float]:
        if not self.request_count:
            return None
        return self.request_seconds / self.request_count

    def estimated_sweep_seconds(self) -> Optional[int]:
        """What reading every application would cost, from what this tenant just measured.

        An estimate you are given before you are asked to agree to the wait -- the number is
        the tenant's own answer time, not a constant baked in from somewhere else.
        """
        per_request = self.seconds_per_request()
        if per_request is None:
            return None
        return int(round(len(self.entries) * per_request))


def run_inventory(
    client: HttpClient,
    *,
    kinds: Tuple[str, ...],
    progress: Optional[Callable[[str], None]] = None,
) -> InventoryResult:
    """One request per kind: ids and names, and no per-application read at all.

    This is what `scan` does when no application was named, because reading an application is a
    request each and a tenant can hold hundreds of them, at roughly a second apiece. Which
    applications to migrate is your decision; the inventory is what that decision is made
    against, and the deep read comes after it, not before.
    """
    result = InventoryResult()
    report = progress or (lambda _message: None)

    for kind in kinds:
        report(f"listing {kind} applications…")
        started = time.monotonic()
        try:
            listing = list_applications(client, kind)
        except ApiError as exc:
            report(f"  listing {kind} applications failed: HTTP {exc.status} {exc.message}")
            result.errors.append(_list_error(kind, exc))
            continue
        result.request_seconds += time.monotonic() - started
        result.request_count += 1
        report(f"  {len(listing)} {kind} applications")
        for entry in listing:
            app_id = str(entry.get("id"))
            result.entries.append(
                {
                    "id": app_id,
                    "kind": kind,
                    "entityType": app_id.split("-", 1)[0],
                    "name": entry.get("name"),
                }
            )
    return result


def run_scan(
    client: HttpClient,
    *,
    kinds: Tuple[str, ...] = ("web", "mobile"),
    only_ids: Optional[Iterable[str]] = None,
    all_applications: bool = False,
    progress: Optional[Callable[[str], None]] = None,
) -> ScanResult:
    """Read the named applications, or every application when `all_applications` is set.

    Neither is the default: `scan` with no selection produces the inventory instead
    (`run_inventory`). When ids are named the enumeration is skipped entirely -- the id says
    which kind it is -- so a two-application probe costs two requests, not the whole tenant.
    """
    result = ScanResult()
    report = progress or (lambda _message: None)

    if only_ids:
        selected: List[str] = []
        for value in only_ids:
            app_id = value.strip()
            if app_id and app_id not in selected:
                selected.append(app_id)
        for index, app_id in enumerate(selected, start=1):
            kind = kind_for_id(app_id)
            if kind is None:
                result.errors.append(
                    {
                        "applicationId": app_id,
                        "kind": None,
                        "stage": "identify",
                        "status": 0,
                        "message": "not a classic web or mobile application entity id",
                    }
                )
                continue
            report(f"reading {kind} {index}/{len(selected)}: {app_id}")
            scan_application(client, kind, {"id": app_id}, result)
        return result

    if not all_applications:
        return result

    for kind in kinds:
        report(f"listing {kind} applications…")
        try:
            listing = list_applications(client, kind)
        except ApiError as exc:
            report(f"  listing {kind} applications failed: HTTP {exc.status} {exc.message}")
            result.errors.append(_list_error(kind, exc))
            continue
        report(f"  reading all {len(listing)} {kind} applications, one request each")
        for index, entry in enumerate(listing, start=1):
            app_id = str(entry.get("id"))
            report(f"  reading {kind} {index}/{len(listing)}: {app_id}")
            scan_application(client, kind, entry, result)
    return result


# --------------------------------------------------------------------------- translation

EVENT_PREFIX = "event_properties."
SESSION_PREFIX = "session_properties."
GRAIL_PREFIXES = (EVENT_PREFIX, SESSION_PREFIX)

# The agent caps the *prefixed* field name at 100 characters and the two prefixes differ in
# length, so an 83-character key is a valid event property and an invalid session property.
# Length is checked after prefixing, against the prefix this property will
# actually carry -- a promotion lengthens the name by two.
MAX_FIELD_NAME = 100
MAX_EVENT_KEY = MAX_FIELD_NAME - len(EVENT_PREFIX)
MAX_SESSION_KEY = MAX_FIELD_NAME - len(SESSION_PREFIX)

KEY_UNSAFE = re.compile(r"[^A-Za-z0-9._]")
KEY_REPLACEMENT = "_"

_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_DIGITS = frozenset("0123456789")

# The rule the agent enforces at runtime, published with its exact pattern at
# https://docs.dynatrace.com/javascriptapi/doc-latest/variables/API.VALID_KEY_REGEX.html
# It is stricter than the one the settings API checks (`^[a-zA-Z0-9._]+$`), so a key can be
# accepted by the API with a `200` and then dropped by the agent on every event, silently --
# which is why this tool validates locally instead of treating a clean write as proof.
#
# ⚠ It applies to the **prefixed field name** -- `event_properties.<key>`, not `<key>` -- and the
# difference is not cosmetic. The first segment may start with a digit, but once the prefix is in
# front the key is no longer the first segment: it sits after a `.`, where a segment must start
# with a letter. So `1a.b` is a valid-looking key that never produces a property. Validating the
# bare key silently accepts keys that are thrown away at runtime.
KEY_AGENT_PATTERN = re.compile(r"^[\dA-Za-z]+(?:\.[A-Za-z][\dA-Za-z]*|_[\dA-Za-z]+)*$")

# The same rule stated at key level, for prose that has to explain it without a prefix. Checked
# equivalent to `KEY_AGENT_PATTERN.match(prefix + key)` over 3913 generated keys, for both
# prefixes. It is documented, not used -- the code matches the real pattern against the real
# field name, so there is no derivation left to drift:
#     ^[A-Za-z][\dA-Za-z]*(?:\.[A-Za-z][\dA-Za-z]*|_[\dA-Za-z]+)*$

# Classic type -> what the value becomes in Grail. Nothing in the settings object records it: a
# captured property is a key plus its capturing steps and nothing else. This table exists to
# report a semantic change, never to fill a field.
TYPE_TO_GRAIL = {
    "STRING": "STRING",
    "LONG_STRING": "STRING",
    "DOUBLE": "NUMBER",
    "LONG": "NUMBER",
    "DATE": None,
}

# Classic type -> the cast the promotion statement wraps the value in. Classic required a type
# on every property, and a numerically typed one really was numeric by the time a query read it:
# a captured value arrives as text, and the declared type is what made it a number. Gen3 has no
# such declaration -- the property is whatever the browser sent, and a value read from the DOM, a
# cookie or the query string is sent as text. `Min`, `Max`, `Avg` and `Sum` apply only to numeric
# properties, so the promotion statement is the last place that can put the declared type back,
# and it casts. Both functions are available to a `dql` processor:
# https://docs.dynatrace.com/docs/platform/openpipeline/reference/dql/openpipeline-dql-functions
TYPE_TO_CAST = {"LONG": "toLong", "DOUBLE": "toDouble"}

# The four strategies the documentation restricts to numeric properties. `First` and `Last` apply
# to any type, which is why only these four make the classic type load-bearing.
NUMERIC_STRATEGIES = ("Min", "Max", "Avg", "Sum")

# Classic aggregation -> the `session_properties_aggregation.<key>` value, one-to-one.
# Mobile spells two of them differently.
AGGREGATION_TO_PIPELINE = {
    "FIRST": "First",
    "LAST": "Last",
    "SUM": "Sum",
    "AVERAGE": "Avg",
    "MINIMUM": "Min",
    "MIN": "Min",
    "MAXIMUM": "Max",
    "MAX": "Max",
}

CAPTURED = "capturedEventProperties"
DECLARED = "allowedApiReportedProperties"


def _flag(name: str, detail: str, *, blocking: bool = False) -> Dict[str, Any]:
    """A flag is a sentence someone will read, plus whether it stops the migration."""
    return {"flag": name, "detail": detail, "blocking": blocking}


def _positional_charset_problem(key: str, *, prefix: str) -> Optional[str]:
    """The agent's positional rule, which is stricter than the schema's `^[a-zA-Z0-9._]+$`.

    Matched against `prefix + key`, which is the string the rule applies to -- see the note on
    KEY_AGENT_PATTERN. A key that passes Settings validation and fails this one is accepted by
    the API and then silently dropped at runtime: both `a..b` and `1a.b` come back `200` from
    `?validateOnly=true`, so the API is not a substitute for this check.
    """
    if not key:
        return "the key is empty"
    if KEY_AGENT_PATTERN.match(prefix + key):
        return None
    # It failed. The branches below exist only to say *why* in a sentence someone can act on;
    # the pattern above is what decides.
    if key[0] in _DIGITS:
        return (
            "a key may not start with a digit -- the agent validates the whole field name "
            f"`{prefix}{key}`, in which the key sits after the prefix's `.`, and a segment "
            "after a `.` has to start with a letter"
        )
    if key[0] in ("_", "."):
        return "a key may not start with `_` or `.`"
    for index, char in enumerate(key):
        following = key[index + 1] if index + 1 < len(key) else ""
        if char == "." and following not in _LETTERS:
            return (
                f"a `.` must be followed by a letter, not {following!r}"
                if following
                else "a key may not end with `.`"
            )
        if char == "_" and following not in _LETTERS and following not in _DIGITS:
            return (
                f"a `_` must be followed by a letter or a digit, not {following!r}"
                if following
                else "a key may not end with `_`"
            )
    return "the key does not match the charset the agent accepts"


def translate_key(classic_key: Any, *, session_scoped: bool) -> Dict[str, Any]:
    """Classic property key -> Grail property key, with every change it had to make reported.

    Four rules in order: strip a leading Grail prefix, because the schema rejects any key that
    *contains* one; replace characters the charset does not allow; check the positional charset
    the agent enforces at runtime; and check the length against the prefix this property will
    carry. Nothing is truncated -- a shortened key is a different key, and choosing it is a
    decision for whoever owns the property.
    """
    budget = MAX_SESSION_KEY if session_scoped else MAX_EVENT_KEY
    field_prefix = SESSION_PREFIX if session_scoped else EVENT_PREFIX
    flags: List[Dict[str, Any]] = []

    if not isinstance(classic_key, str) or not classic_key:
        return {
            "classicKey": classic_key if isinstance(classic_key, str) else None,
            "key": None,
            "changed": False,
            "budget": budget,
            "flags": [_flag("missing-key", "the classic property carries no `key`", blocking=True)],
            "blocked": True,
        }

    key = classic_key
    for grail_prefix in GRAIL_PREFIXES:
        if key.startswith(grail_prefix):
            key = key[len(grail_prefix) :]
            flags.append(
                _flag(
                    "prefix-stripped",
                    f"the classic key already began with `{grail_prefix}`, which the Grail schema "
                    "rejects in a property key; the prefix is added by the namespace, not by "
                    "the key",
                )
            )
            break

    replaced = KEY_UNSAFE.sub(KEY_REPLACEMENT, key)
    if replaced != key:
        offenders = sorted({char for char in key if KEY_UNSAFE.match(char)})
        flags.append(
            _flag(
                "characters-replaced",
                "characters outside `[A-Za-z0-9._]` were replaced with `"
                + KEY_REPLACEMENT
                + "`: "
                + ", ".join(repr(char) for char in offenders)
                + ". Queries and dashboards that name the old key have to be updated",
            )
        )
        key = replaced

    if any(prefix in key for prefix in GRAIL_PREFIXES):
        flags.append(
            _flag(
                "prefix-embedded",
                "the key still contains `event_properties.` or `session_properties.` after the "
                "leading prefix was stripped; the schema rejects a key that contains either "
                "anywhere, so this one has to be renamed by hand",
                blocking=True,
            )
        )

    problem = _positional_charset_problem(key, prefix=field_prefix)
    if problem is not None:
        flags.append(
            _flag(
                "charset-rejected",
                f"{problem}. The Settings API accepts this key and the agent then drops the "
                "property silently, so it has to be renamed rather than written and watched",
                blocking=True,
            )
        )

    if len(key) > budget:
        flags.append(
            _flag(
                "key-too-long",
                f"the key is {len(key)} characters and the budget is {budget} -- a field name "
                f"is capped at {MAX_FIELD_NAME} including the `{field_prefix}` prefix. Shortening it "
                "is a decision about what the property is called, so it is yours to make",
                blocking=True,
            )
        )

    return {
        "classicKey": classic_key,
        "key": key,
        "changed": key != classic_key,
        "budget": budget,
        "flags": flags,
        "blocked": any(flag["blocking"] for flag in flags),
    }


def _step(capture_type: str, capture_value: Optional[str] = None) -> Dict[str, Any]:
    """`JSON_PARSER` is the one step with no `captureValue` -- the schema hides the field."""
    if capture_type == "JSON_PARSER":
        return {"captureType": "JSON_PARSER"}
    return {"captureType": capture_type, "captureValue": capture_value or ""}


def normalise_selector(selector: str) -> Tuple[str, bool]:
    """`'` -> `"` in every selector. Not a tidiness rule -- a correctness one.

    The Gen3 configuration rides in a single-quoted HTML attribute carrying raw JSON, and
    `JSON.stringify` does not escape `'`, so one single quote truncates the configuration and
    **the whole agent fails to initialise**. Classic stores quotes byte-for-byte, so the quote
    read here is the one that was typed, and normalising it is this tool's job rather than
    something to hand back as a manual fix.
    """
    return selector.replace("'", '"'), "'" in selector


def translate_javascript_expression(expression: str) -> Dict[str, Any]:
    """Classic dotted expression -> ordered `capturingSteps`, in five rules.

    `localStorage.userInformation.$username` becomes property, property, JSON parse, property --
    the order the steps are evaluated in, which is the order they have to be written in.
    """
    flags: List[Dict[str, Any]] = []

    # Rule 2 first, because rule 1 would rewrite `a["b"]` into something that looks fine.
    if re.search(r"\[\s*[\"']", expression):
        flags.append(
            _flag(
                "quoted-bracket-notation",
                "quoted bracket notation (`a[\"b\"]`) does not work in the classic agent either -- it "
                "captures nothing today, so there is nothing working to preserve. Rewrite it in "
                "dotted form and it migrates",
                blocking=True,
            )
        )
        return {"steps": [], "flags": flags, "blocked": True}

    # Rule 1: unquoted brackets become dots, mirroring Gen2's own rewrite.
    dotted = re.sub(r"\[([^\]]*)\]", r".\1", expression)
    if dotted != expression:
        flags.append(
            _flag(
                "bracket-notation-flattened",
                "index notation was flattened to dots, which is what Gen2 does to it internally",
            )
        )

    segments = dotted.split(".")
    if any(segment == "" for segment in segments):
        flags.append(
            _flag(
                "empty-expression-segment",
                f"the capture expression {expression!r} has an empty segment, so it resolves to "
                "nothing; it has to be corrected in classic first",
                blocking=True,
            )
        )
        return {"steps": [], "flags": flags, "blocked": True}

    steps: List[Dict[str, Any]] = []
    for index, segment in enumerate(segments):
        if segment.startswith("$"):
            # Rule 5: a chain cannot begin by parsing something it has not read yet.
            if index == 0:
                flags.append(
                    _flag(
                        "json-parser-first",
                        "the expression starts with a `$` segment, which would make JSON parsing "
                        "the first step; there is nothing to parse until a value has been read",
                        blocking=True,
                    )
                )
                return {"steps": [], "flags": flags, "blocked": True}
            steps.append(_step("JSON_PARSER"))
            steps.append(_step("PROPERTY_ACCESSOR", segment[1:]))
        else:
            steps.append(_step("PROPERTY_ACCESSOR", segment))

    if any(step["captureType"] == "JSON_PARSER" for step in steps):
        flags.append(
            _flag(
                "json-parsed-unconditionally",
                "Gen2 parsed JSON only when the literal `$`-named property was absent; Gen3 "
                "parses every time and hard-fails on input that is not a string. Worth a look at "
                "whether the source value is always JSON",
            )
        )
    return {"steps": steps, "flags": flags, "blocked": False}


def translate_capture_expression(capture_type: Any, capturing_name: Any) -> Dict[str, Any]:
    """Classic `metaDataCaptureSettings` entry -> Gen3 `capturingSteps`.

    The selector lives in `capturingName`; `name` is a display label nothing references, and
    this tool must never read it.
    """
    expression = capturing_name if isinstance(capturing_name, str) else ""
    if not expression:
        return {
            "steps": [],
            "flags": [
                _flag(
                    "missing-capture-expression",
                    "the capture setting carries no `capturingName`, so there is no expression "
                    "to translate",
                    blocking=True,
                )
            ],
            "blocked": True,
        }

    if capture_type == "COOKIE":
        return {"steps": [_step("COOKIE_ACCESSOR", expression)], "flags": [], "blocked": False}

    if capture_type == "JAVA_SCRIPT_VARIABLE":
        # `window.foo` genuinely means `window.window.foo`, because Gen2 resolves segment 0
        # against `window` -- so a leading `window.` is never stripped.
        return translate_javascript_expression(expression)

    if capture_type == "META_TAG":
        selector, _ = normalise_selector(f'meta[name="{expression}"]')
        return {
            "steps": [
                _step("QUERY_SELECTOR", selector),
                _step("DOM_ATTRIBUTE_ACCESSOR", "content"),
            ],
            "flags": [],
            "blocked": False,
        }

    if capture_type == "CSS_SELECTOR":
        if "@" not in expression:
            return {
                "steps": [],
                "flags": [
                    _flag(
                        "selector-text-content",
                        "the selector captures an element's text, and the new capture has no "
                        "`innerText` fallback -- a selector-only chain captures nothing at "
                        "all. Adding an attribute to read makes it migratable; otherwise "
                        "report the value through the API instead",
                        blocking=True,
                    )
                ],
                "blocked": True,
            }
        raw_selector, attribute = expression.rsplit("@", 1)
        selector, had_quote = normalise_selector(raw_selector)
        flags: List[Dict[str, Any]] = []
        if had_quote:
            flags.append(
                _flag(
                    "selector-quotes-normalised",
                    "single quotes in the selector were rewritten as double quotes; a single "
                    "quote in a selector truncates the agent's configuration and stops it "
                    "initialising",
                )
            )
        if not attribute:
            flags.append(
                _flag(
                    "selector-empty-attribute",
                    "the selector ends in `@` with no attribute name, so there is nothing to "
                    "read from the matched element",
                    blocking=True,
                )
            )
            return {"steps": [], "flags": flags, "blocked": True}
        return {
            "steps": [
                _step("QUERY_SELECTOR", selector),
                _step("DOM_ATTRIBUTE_ACCESSOR", attribute),
            ],
            "flags": flags,
            "blocked": False,
        }

    if capture_type == "QUERY_STRING":
        # Gen3 has no query-string accessor, but the first property step is a `window` lookup,
        # so `location` then `search` resolves and yields the raw query string. Splitting the
        # parameter out of it is an OpenPipeline job, which is why this one migrates in two
        # parts rather than being blocked -- and the split is generated, because Gen2's reading
        # of a query string is fixed code rather than configuration.
        return {
            "steps": [
                _step("PROPERTY_ACCESSOR", "location"),
                _step("PROPERTY_ACCESSOR", "search"),
            ],
            "flags": [
                _flag(
                    "query-string-two-part",
                    f"the capture yields the whole query string, not the {expression!r} "
                    "parameter; a generated pipeline rule splits the parameter out and writes it "
                    "back under the same key",
                ),
                _flag(
                    "query-string-case-sensitivity",
                    f"the parameter name {expression!r} is matched ignoring case, as Gen2 "
                    "matched it, and the value is taken as it appears in the URL -- not "
                    "decoded, as before. Of repeated parameters the first non-empty one wins",
                ),
                _flag(
                    "query-string-hash-route",
                    "on a page whose route is in the URL fragment (`/#/page?x=1`), Gen2 also "
                    "read a query string written after the `#`. The browser does not count that "
                    "as the query string, so the capture does not see it and the property stays "
                    "empty on such pages",
                ),
            ],
            "blocked": False,
            "pipeline": {"rule": "query-string-split", "parameter": expression},
        }

    if capture_type == "JAVA_SCRIPT_FUNCTION":
        return {
            "steps": [],
            "flags": [
                _flag(
                    "capture-type-unsupported",
                    "Gen3 has no function accessor, and Gen2 restricted this type to a short "
                    "allow-list of third-party globals. There is no path for it",
                    blocking=True,
                )
            ],
            "blocked": True,
        }

    if capture_type == "RESPONSE_HEADER":
        return {
            "steps": [],
            "flags": [
                _flag(
                    "capture-type-blocked-by-layer",
                    "the agent implements response-header capture, but the setting lives in a "
                    "request array that Settings 2.0 cannot populate -- so this is blocked by "
                    "missing cluster and UI support, not by the agent, and a path is expected",
                    blocking=True,
                )
            ],
            "blocked": True,
        }

    return {
        "steps": [],
        "flags": [
            _flag(
                "capture-type-unknown",
                f"capture type {capture_type!r} is not one this build knows how to translate",
                blocking=True,
            )
        ],
        "blocked": True,
    }


def classify_property(prop: Dict[str, Any], *, kind: str) -> Dict[str, Any]:
    """The decision table: `origin` x scope decides everything.

    Scope reads `storeAsSessionProperty` and nothing else. `aggregation` comes back as `LAST` on
    every classic property, including action-only ones, so it carries no scope information
    whatever -- on web and on mobile alike.
    """
    origin = prop.get("origin")
    session_scoped = prop.get("storeAsSessionProperty") is True
    action_scoped = prop.get("storeAsUserActionProperty") is True

    if origin == "SERVER_SIDE_REQUEST_ATTRIBUTE":
        return {
            "row": 5,
            "sessionScoped": session_scoped,
            "actionScoped": action_scoped,
            "settingsField": None,
            "codeChange": False,
            "decisionRequired": False,
            "blocked": True,
            "reason": "a request attribute is read server-side by OneAgent and a browser only "
            "sees the headers it receives, so there is no Gen3 path today. Request and response "
            "header capture will cover some of these cases once it has cluster and UI support -- "
            "some, not most",
        }

    # Mobile has no `capturedEventProperties`, no capturing steps and no accessor enum: there is
    # no DOM and no cookie to read. Every mobile property is declaration-plus-code-change.
    if kind == "mobile" or origin == "API":
        return {
            "row": 4 if session_scoped else 3,
            "sessionScoped": session_scoped,
            "actionScoped": action_scoped,
            "settingsField": DECLARED,
            "codeChange": True,
            "decisionRequired": False,
            "blocked": False,
            "reason": None,
        }

    if origin == "JAVASCRIPT_API":
        return {
            "row": 4 if session_scoped else 3,
            "sessionScoped": session_scoped,
            "actionScoped": action_scoped,
            "settingsField": DECLARED,
            "codeChange": True,
            "decisionRequired": False,
            "blocked": False,
            "reason": None,
        }

    if origin == "META_DATA":
        return {
            "row": 2 if session_scoped else 1,
            "sessionScoped": session_scoped,
            "actionScoped": action_scoped,
            "settingsField": CAPTURED,
            "codeChange": False,
            # Row 2 is the one fork the tool must not resolve on its own: accept event scope,
            # keep session scope with code, or keep it with an OpenPipeline promotion.
            "decisionRequired": session_scoped,
            "blocked": False,
            "reason": None,
        }

    return {
        "row": None,
        "sessionScoped": session_scoped,
        "actionScoped": action_scoped,
        "settingsField": None,
        "codeChange": False,
        "decisionRequired": False,
        "blocked": True,
        "reason": f"origin {origin!r} is not one this build knows, so where the property belongs "
        "cannot be decided; report it and leave it alone",
    }


# Row 2 is the one fork the tool refuses to resolve on its own. The three options are described
# once in the plan artifact; a row names the letters, not the paragraphs.
ROW_2_OPTIONS = {
    "A": "Accept event scope. No code change, and the migration is complete the moment the "
    "settings object is applied. The property lands on every event that captures it instead of "
    "once per session, so queries aggregate over user.events with takeFirst/takeLast instead of "
    "reading user.sessions.",
    "B": "Keep session scope, with code. Declare the key and call "
    "dynatrace.sendSessionPropertyEvent() where the value becomes known. The classic capture expression says what to read; you "
    "supply the when.",
    "C": "Keep session scope, without code. Capture as an event property and promote it into "
    "session_properties with an OpenPipeline rule. No release needed and true session scope is "
    "preserved, at the cost of owning a pipeline rule -- and it is the only option that keeps "
    "the classic aggregation setting.",
}

# What the user is told the three options are called. The letters are the CLI's (--row2), and
# a user who never saw the decision table cannot know what "option C" means -- so nothing a
# user reads names a letter or a row.
ROW_2_LABELS = {
    "A": "per event",
    "B": "on the session, set by your code",
    "C": "on the session, set by a pipeline rule",
}


# Classic scoped a configured property to the action **or** to the session, one or the other.
# A promoted property (row 2C) ends up in both namespaces: the capture writes
# `event_properties.<key>` and the promotion copies it onto the session. The event property is
# the carrier, not the destination -- classic never produced one for a session-scoped property --
# so the migration offers to remove it once it has been read.
#
# ⚠ Offered, never taken silently. The default is to keep it, for three reasons: a query written
# against `event_properties.<key>` during a parallel run stops returning; the two counts side by
# side are what tell "the capture works and the promotion does not" from "nothing is arriving";
# and it saves nothing -- a session property bills on presence in the session either way.
DROP_SOURCE_RULE = "source-field-removal"

# Why a carrier is being removed. The two look identical in the pipeline and read very
# differently in the plan: one is a property you configured, the other a key this tool
# invented to carry a user tag.
DROP_REASON_PROMOTED = "promoted-to-a-session-property"
DROP_REASON_USER_TAG = "lifted-to-user-identifier"


def _removal_rule(key: str, *, reason: str, for_option: Optional[str] = None) -> Dict[str, Any]:
    """Remove the carrier event property, once whatever reads it has run.

    ⚠ `runsLast` is a correctness requirement, not a preference. Processors in a stage run in
    array order, so a removal placed before the statement that reads the field deletes the
    input instead of the leftover. `openpipeline_payload` collects every removal and appends it
    after all of an application's other processors -- which also covers the case where one
    captured property feeds both a promotion and a user tag.

    The matcher gates on the field for the same reason every other matcher here does: it costs
    nothing on the happy path and keeps the processor off events that never carried the value.
    """
    source = f"{EVENT_PREFIX}{key}"
    return {
        "rule": DROP_SOURCE_RULE,
        "reason": reason,
        "forOption": for_option,
        # Carried on the rule itself, because a user tag's removal never passes through
        # `pipeline_change_list` -- which is where a property's rules pick their key up.
        "key": key,
        "stage": "PROCESSING",
        "table": "user.events",
        "processor": "dql",
        "runsLast": True,
        "matcher": f"isNotNull({source})",
        "statement": f"fieldsRemove {source}",
        "field": source,
    }


def _promotion_rule(key: str, aggregation: Any, classic_type: Any) -> Dict[str, Any]:
    """The row-2C promotion, in the documented shape.

    Two `fieldsAdd` statements, never `fieldsRename` -- which destroys the event property and
    cannot set the aggregation. The matcher gates on the source field: the value copy is
    self-guarding, but the aggregation statement assigns a literal, so an ungated matcher writes
    an orphan directive onto every event the pipeline sees.

    The value is cast whenever the classic type is numeric, and which cast is a lookup rather
    than a judgement call -- the classic property is declared `LONG` or `DOUBLE`. Without it a
    numeric strategy has no numeric property to apply to and the session silently keeps the last
    reported value instead, which is the documented default.
    """
    strategy = AGGREGATION_TO_PIPELINE.get(str(aggregation), "Last")
    cast = TYPE_TO_CAST.get(str(classic_type))
    source = f"event_properties.{key}"
    value = f"{cast}({source})" if cast else source
    return {
        "rule": "session-property-promotion",
        "forOption": "C",
        "stage": "PROCESSING",
        "table": "user.events",
        "processor": "dql",
        "matcher": f"isNotNull({source})",
        "statement": (
            f"fieldsAdd session_properties.{key} = {value}, "
            f'session_properties_aggregation.{key} = "{strategy}"'
        ),
        "aggregation": strategy,
        "classicAggregation": aggregation,
        "classicType": classic_type,
        "cast": cast,
    }


# ------------------------------------------------- classic extractions, as DQL expressions
#
# A classic cleanup rule is a Java regular expression with one capture group, applied
# server-side to the captured value. DQL has no regex extraction: `matchesRegex` answers yes or
# no on the whole value, and DPL -- reachable inline through `parse` -- is anchored and never
# backtracks. So a rule is translated only where the translation is **exact**, built from
# pieces measured one by one against Grail, and every other rule stays yours to write.
#
# The exact subset: an optional `^`, a literal, one group, a literal. The group is either a
# literal or one run -- `.`, a class, `\d` `\s` `\w` or their negations -- with any quantifier,
# greedy or lazy. Every rule outside it is reported with the construct that put it outside.
#
# ⚠ Three measured traps, each shaping what is emitted:
#   - DPL's bounded `{m,n}` counts **bytes**, and cut `é` in half. Runs are matched unbounded
#     and counted afterwards in DQL, which counts characters.
#   - DPL refuses every non-ASCII character in a pattern, so every class member is written as
#     `\xHH`, and a class naming a non-ASCII character is not translated.
#   - DPL does not backtrack, so a greedy group followed by a literal is never one pattern:
#     the run is measured by DPL and the literal found by `lastIndexOf` within it.
#
# Not exact in one respect, deliberately accepted: DQL counts UTF-16 units and Java counts
# code points, so a counted quantifier sees a character outside the Basic Multilingual Plane
# -- an emoji -- as two.

_ASCII = frozenset(range(0x80))
_DIGIT = frozenset(range(0x30, 0x3A))
_WORD = _DIGIT | frozenset(range(0x41, 0x5B)) | frozenset(range(0x61, 0x7B)) | {0x5F}
# Java's `\s`, without UNICODE_CHARACTER_CLASS: ASCII only, vertical tab included.
_SPACE = frozenset(b" \t\n\x0b\f\r")
# A class is the ASCII members it names, and whether it also holds every non-ASCII character
# -- which a negated class does, and which is the only way a class can mention non-ASCII here.
_SHORTHAND = {
    "d": (_DIGIT, False),
    "D": (_ASCII - _DIGIT, True),
    "s": (_SPACE, False),
    "S": (_ASCII - _SPACE, True),
    "w": (_WORD, False),
    "W": (_ASCII - _WORD, True),
}
_CHAR_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "f": "\f", "a": "\x07", "e": "\x1b"}
_METACHARS = frozenset("\\^$.|?*+()[]{}")
_QUANTIFIERS = frozenset("?*+{")
_QUANTIFIER_BOUNDS = re.compile(r"\{(\d+)(,(\d*))?\}")
# Java's `.` stops at five line terminators. These are the four besides `\n`; they are folded
# onto `\n` before a `.` run is measured, because DPL cannot name the three non-ASCII ones.
_DOT_ALSO_STOPS_AT = ("\r", "\u0085", "\u2028", "\u2029")


class Untranslatable(Exception):
    """A cleanup rule outside the exactly-translated subset. The message names the construct."""


class _RuleReader:
    def __init__(self, rule: str) -> None:
        self.rule = rule
        self.at = 0

    def peek(self, ahead: int = 0) -> str:
        index = self.at + ahead
        return self.rule[index] if index < len(self.rule) else ""

    def take(self) -> str:
        char = self.peek()
        self.at += 1
        return char

    def done(self) -> bool:
        return self.at >= len(self.rule)


def _escaped(reader: _RuleReader) -> Tuple[str, Optional[Tuple[frozenset, bool]]]:
    """After a backslash: one character, or a shorthand class."""
    char = reader.take()
    if not char:
        raise Untranslatable("a trailing backslash")
    if char in _SHORTHAND:
        return "", _SHORTHAND[char]
    if char in _CHAR_ESCAPES:
        return _CHAR_ESCAPES[char], None
    if char in "xu":
        width = 2 if char == "x" else 4
        digits = reader.rule[reader.at:reader.at + width]
        if len(digits) != width or any(d not in "0123456789abcdefABCDEF" for d in digits):
            raise Untranslatable(f"`\\{char}` without {width} hex digits")
        reader.at += width
        return chr(int(digits, 16)), None
    if char.isascii() and char.isalnum():
        raise Untranslatable(f"`\\{char}`")
    return char, None


def _literal_run(reader: _RuleReader) -> str:
    """Characters that match themselves, up to the first thing that does not."""
    out: List[str] = []
    while not reader.done():
        char = reader.peek()
        if char == "\\":
            mark = reader.at
            reader.take()
            text, shorthand = _escaped(reader)
            if shorthand is not None:
                reader.at = mark
                break
        elif char in _METACHARS:
            break
        else:
            text = reader.take()
        if reader.peek() in _QUANTIFIERS:
            raise Untranslatable("a quantifier on a literal character")
        out.append(text)
    return "".join(out)


def _class_member(reader: _RuleReader) -> Tuple[str, Optional[Tuple[frozenset, bool]]]:
    char = reader.take()
    if char == "\\":
        return _escaped(reader)
    return char, None


def _char_class(reader: _RuleReader) -> Tuple[frozenset, bool]:
    reader.take()
    negated = reader.peek() == "^"
    if negated:
        reader.take()
    if reader.peek() == "]":
        raise Untranslatable("a `]` first in a character class")
    members: set = set()
    nonascii = False
    while True:
        char = reader.peek()
        if not char:
            raise Untranslatable("an unclosed character class")
        if char == "]":
            reader.take()
            break
        if char == "[" or reader.rule.startswith("&&", reader.at):
            raise Untranslatable("a nested or intersected character class")
        low, shorthand = _class_member(reader)
        if shorthand is not None:
            members |= shorthand[0]
            nonascii = nonascii or shorthand[1]
            continue
        if reader.peek() == "-" and reader.peek(1) not in ("]", ""):
            reader.take()
            high, shorthand = _class_member(reader)
            if shorthand is not None or ord(high) < ord(low):
                raise Untranslatable("a character-class range Java would refuse")
            span = range(ord(low), ord(high) + 1)
        else:
            span = range(ord(low), ord(low) + 1)
        if span[-1] > 0x7F:
            raise Untranslatable("a non-ASCII character in a character class")
        members.update(span)
    named = frozenset(members)
    return (_ASCII - named, not nonascii) if negated else (named, nonascii)


def _quantifier(reader: _RuleReader) -> Tuple[int, Optional[int], bool]:
    char = reader.peek()
    if char not in _QUANTIFIERS:
        return 1, 1, False
    if char == "{":
        bounds = _QUANTIFIER_BOUNDS.match(reader.rule, reader.at)
        if not bounds:
            raise Untranslatable("a `{` that is not a quantifier")
        reader.at = bounds.end()
        low = int(bounds.group(1))
        if bounds.group(2) is None:
            high: Optional[int] = low
        else:
            high = int(bounds.group(3)) if bounds.group(3) else None
    else:
        reader.take()
        low, high = {"*": (0, None), "+": (1, None), "?": (0, 1)}[char]
    if high is not None and high < low:
        raise Untranslatable("a quantifier whose upper bound is below its lower one")
    lazy = reader.peek() == "?"
    if lazy:
        reader.take()
    if reader.peek() == "+":
        raise Untranslatable("a possessive quantifier")
    return low, high, lazy


def _group(reader: _RuleReader) -> Dict[str, Any]:
    reader.take()
    if reader.peek() == "?":
        if reader.peek(1) == "<" and reader.peek(2) not in ("=", "!", ""):
            close = reader.rule.find(">", reader.at)
            if close < 0:
                raise Untranslatable("an unterminated group name")
            reader.at = close + 1
        else:
            raise Untranslatable("a group with flags, or a lookaround")
    start = reader.at
    char = reader.peek()
    run: Optional[Tuple[frozenset, bool, bool]] = None
    if char == ".":
        reader.take()
        run = (_ASCII - {0x0A, 0x0D}, True, True)
    elif char == "[":
        run = (*_char_class(reader), False)
    elif char == "\\":
        reader.take()
        text, shorthand = _escaped(reader)
        if shorthand is not None:
            run = (*shorthand, False)
        elif reader.peek() in _QUANTIFIERS:
            run = (frozenset({ord(text)}), False, False) if text.isascii() else None
        if run is None and reader.peek() in _QUANTIFIERS:
            raise Untranslatable("a non-ASCII character repeated inside the capture group")
    elif char and char not in _METACHARS:
        reader.take()
        if reader.peek() in _QUANTIFIERS:
            if not char.isascii():
                raise Untranslatable("a non-ASCII character repeated inside the capture group")
            run = (frozenset({ord(char)}), False, False)
    if run is not None:
        if not run[0] and not run[1]:
            raise Untranslatable("an empty character class")
        low, high, lazy = _quantifier(reader)
        group: Dict[str, Any] = {"run": run, "low": low, "high": high, "lazy": lazy}
    else:
        reader.at = start
        literal = _literal_run(reader)
        if not literal:
            raise Untranslatable(
                f"`{reader.peek()}` inside the capture group" if reader.peek() != ")"
                else "an empty capture group"
            )
        group = {"literal": literal}
    if reader.peek() != ")":
        raise Untranslatable("more than one element inside the capture group")
    reader.take()
    if reader.peek() in _QUANTIFIERS:
        raise Untranslatable("a quantified or optional capture group")
    return group


def _unexpected(reader: _RuleReader) -> str:
    char = reader.peek()
    named = {
        "": "no capture group",
        "$": "`$`, which in Java also matches before a final line break",
        "|": "`|` (alternation)",
        "(": "a second group",
        ".": "`.` outside the capture group",
        "[": "a character class outside the capture group",
        "\\": "a character class outside the capture group",
    }
    return named.get(char, f"`{char}` outside the capture group")


def parse_cleanup_rule(rule: str) -> Dict[str, Any]:
    """A classic cleanup rule in the translated subset, as parts -- or `Untranslatable`."""
    reader = _RuleReader(rule)
    anchored = reader.peek() == "^"
    if anchored:
        reader.take()
    prefix = _literal_run(reader)
    if reader.peek() != "(":
        raise Untranslatable(_unexpected(reader))
    group = _group(reader)
    suffix = _literal_run(reader)
    if not reader.done():
        raise Untranslatable(_unexpected(reader))
    return {"anchored": anchored, "prefix": prefix, "suffix": suffix, **group}


_DQL_STRING_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def dql_string(text: str) -> str:
    """A DQL string literal: backslash and quote escaped, every control character spelled out."""
    out = []
    for char in text:
        if char in _DQL_STRING_ESCAPES:
            out.append(_DQL_STRING_ESCAPES[char])
        elif ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F or char in "\u2028\u2029":
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _utf16_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _dpl_members(members: Iterable[int]) -> str:
    """ASCII code points as a DPL class body, each one `\\xHH` -- DPL takes no other spelling
    for a metacharacter reliably, and no non-ASCII character at all."""
    spans: List[List[int]] = []
    for code in sorted(members):
        if spans and code == spans[-1][1] + 1:
            spans[-1][1] = code
        else:
            spans.append([code, code])
    return "".join(
        f"\\x{low:02X}" if low == high else f"\\x{low:02X}-\\x{high:02X}" for low, high in spans
    )


def _run_of(value: str, run: Tuple[frozenset, bool, bool], *, skip: bool = False) -> str:
    """The longest run of the class at the start of `value` -- after the first member, with `skip`.

    Matched unbounded, always: a bounded DPL quantifier counts bytes.
    """
    members, nonascii, dot = run
    if dot:
        for terminator in _DOT_ALSO_STOPS_AT:
            value = f"arrayToString(splitString({value}, {dql_string(terminator)}), delimiter: \"\\n\")"
    outside = _ASCII - members if nonascii else members
    if nonascii and not outside:
        return value
    inside, other = (f"[^{_dpl_members(outside)}]*", f"[{_dpl_members(outside)}]*") if nonascii else (
        f"[{_dpl_members(members)}]*", f"[^{_dpl_members(members)}]*"
    )
    pattern = f"{other} {inside}:v" if skip else f"{inside}:v"
    return f"parse({value}, {dql_string(pattern)})"


def _group_value(rest: str, parsed: Dict[str, Any], *, run: Optional[str] = None) -> str:
    """What the group captures when the match starts at the beginning of `rest`, or null."""
    suffix = parsed["suffix"]
    if "literal" in parsed:
        literal = parsed["literal"]
        return f"if(startsWith({rest}, {dql_string(literal + suffix)}), {dql_string(literal)})"
    low, high, lazy = parsed["low"], parsed["high"], parsed["lazy"]
    run = run or _run_of(rest, parsed["run"])
    capped = run if high is None else f"substring({run}, from: 0, to: {high})"
    if not suffix:
        if lazy:
            return f"if(stringLength({run}) >= {low}, substring({run}, from: 0, to: {low}))"
        return capped if low == 0 else f"if(stringLength({run}) >= {low}, {capped})"
    literal = dql_string(suffix)
    if lazy:
        # The shortest run the suffix can follow: its first occurrence at or after the minimum.
        at = f"indexOf({rest}, {literal}, from: {low})"
        return (
            f"if({at} >= {low} and {at} <= stringLength({capped}), "
            f"substring({rest}, from: 0, to: {at}))"
        )
    # The longest: the last occurrence of the suffix that starts within the run.
    window = f"substring({rest}, from: 0, to: stringLength({capped}) + {_utf16_length(suffix)})"
    at = f"lastIndexOf({window}, {literal})"
    return f"if({at} >= {low}, substring({rest}, from: 0, to: {at}))"


def _overlaps_itself(text: str) -> bool:
    return any(text[:size] == text[-size:] for size in range(1, len(text)))


def cleanup_expression(rule: str, field: str) -> str:
    """The DQL that yields what `rule` extracted from `field`, null where it matched nothing.

    The null is this function's; `cleanup_rule_entry` wraps it so the captured value stands in.

    Classic searches the value rather than matching all of it -- `User: (\\S{1,40}) \\(id`
    extracted from a value that went on past `(id`. So an unanchored rule tries every
    occurrence of its leading literal in order and keeps the first that matches, which is the
    search done literally; it is exact only when that literal cannot overlap itself, because
    `splitString` finds non-overlapping occurrences. Raises `Untranslatable`.
    """
    parsed = parse_cleanup_rule(rule)
    prefix = parsed["prefix"]
    if parsed["anchored"]:
        if not prefix:
            return _group_value(field, parsed)
        rest = f"substring({field}, from: {_utf16_length(prefix)})"
        return f"if(startsWith({field}, {dql_string(prefix)}), {_group_value(rest, parsed)})"
    if prefix:
        if _overlaps_itself(prefix):
            raise Untranslatable(
                f"a literal before the group, {prefix!r}, that can overlap itself"
            )
        parts = f"splitString({field}, {dql_string(prefix)})"
        rest = f"arrayToString(arraySlice({parts}, from: iIndex()), delimiter: {dql_string(prefix)})"
        return (
            f"arrayFirst(arrayRemoveNulls(iCollectArray(if(iIndex() >= 1 and "
            f"isNotNull({parts}[]), {_group_value(rest, parsed)}))))"
        )
    if "literal" in parsed:
        literal = parsed["literal"]
        return (
            f"if(contains({field}, {dql_string(literal + parsed['suffix'])}), "
            f"{dql_string(literal)})"
        )
    if not parsed["suffix"] and parsed["low"] == 0:
        # A group that may be empty matches at the very first position.
        return _group_value(field, parsed)
    if not parsed["suffix"] and parsed["low"] == 1:
        # The first run anywhere in the value.
        return _group_value(field, parsed, run=_run_of(field, parsed["run"], skip=True))
    raise Untranslatable(
        "no literal before the group, which leaves every position a possible start"
    )


def translate_cleanup_rule(rule: Any, field: str) -> Dict[str, Any]:
    """`{"expression": ...}` when the rule is in the exact subset, `{"untranslatable": why}` if not."""
    if not isinstance(rule, str) or not rule:
        return {"untranslatable": "no cleanup rule"}
    try:
        return {"expression": cleanup_expression(rule, field)}
    except Untranslatable as exc:
        return {"untranslatable": str(exc)}


def query_parameter_expression(field: str, parameter: str) -> str:
    """The DQL that reads one parameter out of a captured `location.search`, as Gen2 read it.

    Gen2's reading, measured from its source: split on `&`, then on `=`, compare the name
    lower-cased, take the part between the first `=` and any second one (`a=b=c` gives `b`)
    with no decoding, and keep the first
    non-empty value -- an empty one is skipped, so a later duplicate can still win.
    """
    query = f'if(startsWith({field}, "?"), substring({field}, from: 1), else: {field})'
    pairs = f'splitString({query}, "&")'
    value = f'splitString({pairs}[], "=")[1]'
    return (
        f'arrayFirst(arrayRemoveNulls(iCollectArray(if(lower(arrayFirst(splitString({pairs}[], '
        f'"="))) == {dql_string(parameter.lower())} and {value} != "", {value}))))'
    )


# The order a property's rules run in, lowest first. See `plan_property`.
PIPELINE_RULE_ORDER = {"query-string-split": 0, "cleanup": 1, "masking": 2}


def cleanup_rule_entry(rule: Any, field: Optional[str], *, supplied: Optional[str]) -> Dict[str, Any]:
    """One classic cleanup rule as a pipeline rule: translated, supplied, or still yours.

    `expression` is what replaces the field's value. A value the rule does not match is kept
    as it was captured, because that is what classic stored: a user tag whose rule matched
    nothing carried the raw value, and did not fall through to the next tag; a property whose
    rule matched nothing kept the raw value too. Both measured. `ignoreCase` folds the value
    whether the rule matched or not, so the fold belongs around this expression, never inside.
    """
    entry: Dict[str, Any] = {
        "rule": "cleanup",
        "reason": "cleanup-rule",
        "table": "user.events",
        "field": field,
        "classicCleanupRule": rule,
    }
    if supplied:
        entry.update(expression=supplied, expressionSource="supplied")
    elif field:
        translated = translate_cleanup_rule(rule, field)
        if "expression" in translated:
            kept = f"coalesce({translated['expression']}, {field})"
            entry.update(expression=kept, expressionSource="translated")
        else:
            entry["untranslatable"] = translated["untranslatable"]
    if entry.get("expression") and field:
        entry["statement"] = f"fieldsAdd {field} = {entry['expression']}"
    return entry


def cleanup_flag(entry: Dict[str, Any]) -> Dict[str, Any]:
    """The flag that says which of the three a cleanup rule became, and what is left to do."""
    rule = entry.get("classicCleanupRule")
    source = entry.get("expressionSource")
    if source == "translated":
        return _flag(
            "cleanup-rule-translated",
            f"classic extracted part of the value with `{rule}`. The pipeline does the same "
            "extraction after ingest, with a generated expression that yields what the rule "
            "yielded, and keeps the value as captured where the rule matched nothing -- as "
            "classic did",
        )
    if source == "supplied":
        return _flag(
            "cleanup-rule-supplied",
            f"classic extracted part of the value with `{rule}`; the pipeline uses the "
            "expression you supplied in its place, as given",
        )
    return _flag(
        "cleanup-rule-is-yours-to-write",
        f"classic extracted part of the value with `{rule}`, and this rule has no exact "
        f"translation ({entry.get('untranslatable') or 'no key to write it to'}). It needs a DQL "
        "expression that yields the same part of the value, written and confirmed with you; "
        "until then the pipeline half cannot be applied",
    )


def plan_property(
    prop: Dict[str, Any],
    *,
    kind: str,
    capture_settings: Dict[Any, Dict[str, Any]],
    row2_option: Optional[str] = None,
    drop_source: bool = False,
    expression: Optional[str] = None,
) -> Dict[str, Any]:
    """One classic property -> one plan row: bucket, key, steps, pipeline rules and flags.

    Everything here is a pure function of what the tenant returned. Nothing it decides is a
    judgement call -- the judgement calls are surfaced as `decisionRequired` and handed up.

    `row2_option` is the answer to the row-2 fork, and **`None` means unanswered**: the row is
    planned, reported and counted, but it claims no settings field and contributes nothing to
    the payload. A migration does not get to decide what its owner should decide, and a default
    here would be a decision taken silently.

    `drop_source` is the answer to the second, smaller question option C raises -- whether the
    carrier `event_properties.<key>` goes once the promotion has read it. It has a default,
    unlike the row-2 fork, and the default is **keep**: removing it is reversible in the
    pipeline but not in the data, and the row that kept it says so either way.

    `expression` is a DQL expression you supplied for the classic cleanup rule (`plan
    --expression`). It replaces the translation, or stands in where there is none.
    """
    classification = classify_property(prop, kind=kind)
    session_scoped = classification["sessionScoped"]
    key_result = translate_key(prop.get("key"), session_scoped=session_scoped)
    key = key_result["key"]

    flags: List[Dict[str, Any]] = list(key_result["flags"])
    steps: List[Dict[str, Any]] = []
    capture: Optional[Dict[str, Any]] = None
    pipeline: List[Dict[str, Any]] = []
    blocked = classification["blocked"] or key_result["blocked"]
    blocked_reason = classification["reason"]

    if classification["settingsField"] == CAPTURED and not classification["blocked"]:
        setting = capture_settings.get(prop.get("metadataId"))
        if setting is None:
            flags.append(
                _flag(
                    "unresolved-capture-setting",
                    f"metadataId {prop.get('metadataId')!r} matches no `metaDataCaptureSettings` "
                    "entry, so what this property captures cannot be read -- and a property whose "
                    "capture rule cannot be resolved looks unmappable when it may not be",
                    blocking=True,
                )
            )
            blocked = True
        else:
            capture = {
                "type": setting.get("type"),
                "capturingName": setting.get("capturingName"),
                "uniqueId": setting.get("uniqueId"),
            }
            translated = translate_capture_expression(
                setting.get("type"), setting.get("capturingName")
            )
            steps = translated["steps"]
            flags.extend(translated["flags"])
            blocked = blocked or translated["blocked"]
            if translated.get("pipeline") and key:
                split = dict(translated["pipeline"])
                field = f"{EVENT_PREFIX}{key}"
                split["field"] = field
                split["statement"] = (
                    f"fieldsAdd {field} = {query_parameter_expression(field, split['parameter'])}"
                )
                pipeline.append(split)
            if setting.get("publicMetadata") is False:
                flags.append(
                    _flag(
                        "privacy-regression",
                        "this property is excluded from capture for visitors who signal "
                        "Do-Not-Track, and Gen3 has no equivalent control -- migrated as-is it "
                        "**will** be captured for everyone. An OpenPipeline masking rule is the "
                        "nearest thing, and it is not equivalent: it masks for every visitor, not "
                        "only for the ones who asked. The real choice is unconditional masking or "
                        "not migrating this property",
                    )
                )
                pipeline.append(
                    {
                        "rule": "masking",
                        "reason": "privacy-regression",
                        "table": "user.events",
                        "field": f"event_properties.{key}" if key else None,
                    }
                )
            if setting.get("useLastValue") is True:
                flags.append(
                    _flag(
                        "use-last-value-lost",
                        "classic kept the last captured value on the action; Gen3 has no "
                        "counterpart, so the captured value is whichever the agent reads",
                    )
                )

    settings_field = classification["settingsField"]
    code_change = classification["codeChange"]
    pending_decision = False

    if classification["decisionRequired"] and not blocked:
        # Row 2: `META_DATA` + session scope. Three dispositions, and the classifier reaches
        # none of them on its own.
        if row2_option is None:
            pending_decision = True
            settings_field = None
        elif row2_option == "A":
            settings_field = CAPTURED
            code_change = False
            flags.append(
                _flag(
                    "session-scope-lost",
                    "the property becomes event-scoped. It lands on every event that "
                    "captures it instead of once per session, so anything reading it from "
                    "`user.sessions` -- a dashboard, a segment, a saved query, an alert -- stops "
                    "seeing it, and DQL over `user.events` has to aggregate with "
                    "takeFirst/takeLast instead",
                )
            )
        elif row2_option == "B":
            settings_field = DECLARED
            code_change = True
            flags.append(
                _flag(
                    "capture-becomes-code",
                    "the property keeps session scope through your code, and the automatic "
                    "capture does not survive. The code-change list carries what classic read as "
                    "the hint for *what* to send; your code decides *when*, with "
                    "dynatrace.sendSessionPropertyEvent()",
                )
            )
        elif row2_option == "C":
            settings_field = CAPTURED
            code_change = False
            if key:
                promotion = _promotion_rule(
                    key, prop.get("aggregation"), prop.get("type")
                )
                promotion["dropsSource"] = bool(drop_source)
                pipeline.append(promotion)
                # Classic gave this property one scope, and it was the session. The capture
                # cannot write a session property, so the event property exists to be read by
                # the promotion -- after which keeping it is a choice rather than the shape of
                # the mechanism. Both answers are recorded on the row, because keeping it is
                # as much a decision as removing it, and a decision has to be visible.
                if drop_source:
                    pipeline.append(
                        _removal_rule(
                            key, reason=DROP_REASON_PROMOTED, for_option="C"
                        )
                    )
                    flags.append(
                        _flag(
                            "event-property-dropped",
                            f"`event_properties.{key}` is removed from the event "
                            "once the pipeline rule has copied it onto the session, so the Grail "
                            "end state matches the single scope classic gave this property. "
                            "Two consequences: a query, dashboard or segment reading "
                            f"`event_properties.{key}` -- including one you kept running "
                            "during a parallel run -- stops returning, and the per-event and "
                            "per-session counts can no longer be compared to tell a broken "
                            "capture from a broken promotion",
                        )
                    )
                else:
                    flags.append(
                        _flag(
                            "event-property-kept-beside-the-session-property",
                            f"the value ends up in both places: the capture writes "
                            f"`event_properties.{key}` and the pipeline rule copies it to "
                            f"`session_properties.{key}`. Classic scoped this property to the "
                            "session only, so the event property is new. It costs nothing -- a "
                            "session property bills on presence in the session either way -- "
                            "and it is worth keeping while you verify. It can be removed in a "
                            "second change, once nothing reads it",
                        )
                    )
                if promotion["cast"]:
                    flags.append(
                        _flag(
                            "promotion-casts-the-value",
                            f"the pipeline rule casts the value with "
                            f"{promotion['cast']}(), because the classic property is typed "
                            f"{prop.get('type')} and {promotion['aggregation']} applies only to "
                            "numeric properties. A captured value that is not a number cannot "
                            "be cast: the session property stays empty for that event, and the "
                            "aggregation directive is written without it",
                        )
                    )
                elif promotion["aggregation"] in NUMERIC_STRATEGIES:
                    flags.append(
                        _flag(
                            "numeric-aggregation-on-a-text-property",
                            f"classic aggregates this property with "
                            f"{promotion['aggregation']}, which applies only to numeric "
                            f"properties, but the classic type is {prop.get('type')} -- so the "
                            "pipeline rule copies the value as it is. The session keeps the last "
                            "reported value instead of the aggregate. If the value really is a "
                            "number, add toLong() or toDouble() around it in the generated "
                            "statement",
                        )
                    )

    grail_type = TYPE_TO_GRAIL.get(str(prop.get("type")), "STRING")
    if str(prop.get("type")) == "DATE":
        flags.append(
            _flag(
                "date-type-unsupported",
                "Gen3 has no date type and does no coercion. The value has to arrive as epoch "
                "milliseconds (a number) or ISO-8601 (a string), and the queries that read it "
                "have to be adjusted",
            )
        )
    if prop.get("cleanupRule"):
        field = f"{EVENT_PREFIX}{key}" if key else None
        extraction = cleanup_rule_entry(prop.get("cleanupRule"), field, supplied=expression)
        pipeline.append(extraction)
        flags.append(cleanup_flag(extraction))
    # Processors run in array order, so the order here is the order the value is rewritten in:
    # the parameter is split out of the query string, the classic extraction is applied to it,
    # and only then is it masked or promoted -- each of which would otherwise act on a value
    # classic never stored.
    pipeline.sort(key=lambda rule: PIPELINE_RULE_ORDER.get(str(rule.get("rule")), 2))
    if prop.get("ignoreCase") is True:
        # `ignoreCase` folds the **value**; `caseInsensitivePropertyKey` folds the **key**.
        # Mapping one onto the other makes the write fail validation, and turns a working legacy
        # configuration into a failed migration.
        flags.append(
            _flag(
                "ignore-case-lost",
                "classic stored this property's **value** in lower case, whether its cleanup "
                "rule matched or not. Latest Dynatrace keeps the case as captured, so a filter "
                "or comparison that expects lower case has to fold it -- in the query, or with "
                "a pipeline rule",
            )
        )
    if prop.get("longStringLength"):
        flags.append(
            _flag(
                "long-string-length-lost",
                f"classic capped this value at {prop.get('longStringLength')} characters; Gen3 "
                "applies one flat limit of 1000 characters to every string property",
            )
        )

    return {
        "classicKey": key_result["classicKey"],
        "uniqueId": prop.get("uniqueId"),
        "displayName": prop.get("displayName"),
        "kind": kind,
        "origin": prop.get("origin"),
        "type": prop.get("type"),
        "grailType": grail_type,
        "aggregation": prop.get("aggregation"),
        "sessionScoped": session_scoped,
        "actionScoped": classification["actionScoped"],
        "row": classification["row"],
        "settingsField": None if blocked else settings_field,
        "codeChange": code_change and not blocked,
        "decisionRequired": classification["decisionRequired"] and not blocked,
        "decisionPending": pending_decision,
        "decision": (
            {
                "chosen": row2_option,
                "options": {letter: ROW_2_OPTIONS[letter] for letter in sorted(ROW_2_OPTIONS)},
            }
            if classification["decisionRequired"] and not blocked
            else None
        ),
        "options": sorted(ROW_2_OPTIONS) if classification["decisionRequired"] and not blocked else [],
        "key": key,
        "keyChanged": key_result["changed"],
        "capture": capture,
        "capturingSteps": steps,
        "pipeline": pipeline,
        # Stated rather than left to be derived from the rule list: whoever reads a row wants
        # the answer to "is the event property still there afterwards" without walking it.
        "dropsEventProperty": any(
            rule.get("rule") == DROP_SOURCE_RULE for rule in pipeline
        ),
        "flags": flags,
        "blocked": blocked,
        "blockedReason": blocked_reason,
    }


def detect_key_collisions(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Two classic keys that translate to one Grail key are never silently coalesced.

    The schema's `UNIQUE` constraint would reject the write anyway ("Duplicate property keys are
    not allowed."), but whoever runs this needs to know *which* two properties collided and why
    -- the cause is almost always a character this tool replaced. Case-differing keys do **not**
    collide: the constraint is exact-case, and classic tolerates legacy pairs like `myProp` /
    `MyProp`, which migrate cleanly.
    """
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if row["blocked"] or not row["key"]:
            continue
        by_key.setdefault(row["key"], []).append(row)

    collisions: List[Dict[str, Any]] = []
    for key, group in sorted(by_key.items()):
        if len(group) < 2:
            continue
        classic_keys = [row["classicKey"] for row in group]
        collisions.append({"key": key, "classicKeys": classic_keys})
        for row in group:
            others = [other for other in classic_keys if other != row["classicKey"]]
            row["flags"].append(
                _flag(
                    "key-collision",
                    f"this key translates to {key!r}, and so does "
                    + ", ".join(repr(other) for other in others)
                    + ". Two classic properties are never merged into one Grail key: one of them "
                    "has to be renamed before either can be written",
                    blocking=True,
                )
            )
            row["blocked"] = True
            row["settingsField"] = None
    return collisions


# ------------------------------------------------------------------- user tags

# Classic user tagging has no Gen3 configuration at all: there is no schema for it, no setting
# to write, and no agent call this tool can make for you -- `identifyUser()` is
# the only thing that sets `user.identifier` from the browser, and configuration-driven capture
# can only ever write `event_properties.*`. So a classic user tag migrates in two halves that
# have to be applied together: a captured event property, and one OpenPipeline statement that
# copies it onto `user.identifier`. Neither half is a user tag on its own.
USER_TAG_FIELD = "user.identifier"
USER_TAG_KEY_PREFIX = "user_tag_"
USER_TAG_RULE = "user-tag"

# Classic stores a tag cropped to 100 characters and says nothing about it. Gen3 crops nowhere
# along the path -- not at capture, not in the pipeline, not in the session rollup. The lifted
# limit is kept rather than reproduced, so nothing here truncates. The number survives because
# `verify` has to compare crop-aware, and because the change is worth saying out loud: a value
# that classic was silently shortening now arrives whole, and anything downstream that matched
# the shortened form stops matching.
CLASSIC_USER_TAG_CROP = 100

# What a `cleanupRule` becomes is an expression only the reader can write. Classic's dialect is
# an undocumented regular-expression subset with exactly one capture group; DQL is wider, so a
# translation always exists and is never mechanical. The statement is authored complete except
# for this token, and a payload still carrying it is refused rather than sent half-right.
CLEANUP_PLACEHOLDER_PREFIX = "<<REPLACE: extract from "


def user_tag_key(tag: Dict[str, Any], index: int) -> str:
    """A stable, legal Gen3 property key for the value one tag reads.

    Keyed off `uniqueId`, which is what classic already uses to identify a tag inside the
    application, so running this tool twice produces the same key. A key derived from the
    position would move the moment somebody reordered the list -- and reordering that list
    already changes which tag wins, so the key would move for a reason unrelated to the key.
    """
    unique_id = tag.get("uniqueId")
    suffix = str(unique_id) if unique_id is not None else f"i{index}"
    return f"{USER_TAG_KEY_PREFIX}{KEY_UNSAFE.sub(KEY_REPLACEMENT, suffix)}"


def _cleanup_placeholder(field: str, rule: str) -> str:
    return f"{CLEANUP_PLACEHOLDER_PREFIX}{field} what `{rule}` extracted>>"


def plan_user_tag(
    tag: Dict[str, Any],
    *,
    index: int,
    capture_settings: Dict[Any, Dict[str, Any]],
    reuse_by_capture_id: Dict[Any, str],
    expressions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """One classic `UserTag` -> one plan row. The array position is carried, because it decides.

    Within a user action the **first** matching entry in `userTags` wins. That is the opposite
    of what a list of OpenPipeline processors does, where the last assignment to a field is the
    one that survives -- so this cannot become one processor per tag. It becomes one `coalesce`,
    which is first-wins by definition and therefore stops depending on execution order at all.
    """
    row: Dict[str, Any] = {
        "index": index,
        "uniqueId": tag.get("uniqueId"),
        "ignoreCase": tag.get("ignoreCase") is True,
        "cleanupRule": tag.get("cleanupRule"),
        "source": None,
        "requestAttributeId": None,
        "key": None,
        "capture": None,
        "capturingSteps": [],
        "reusesCaptureOf": None,
        "pendingExpression": False,
        "blocked": False,
        "blockedReason": None,
        "flags": [],
    }
    flags: List[Dict[str, Any]] = row["flags"]
    expressions = expressions or {}

    attribute = tag.get("serverSideRequestAttribute")
    if attribute is not None:
        # Not a gap that closes later. `builtin:rum.web.capture-properties` reads the browser,
        # and a request attribute is evaluated server-side against the trace -- there is nothing
        # in the browser for a capturing step to read and nothing on the RUM event for a
        # pipeline statement to copy.
        row["source"] = "request-attribute"
        row["requestAttributeId"] = attribute
        row["blocked"] = True
        row["blockedReason"] = "request-attribute-unsupported"
        flags.append(
            _flag(
                "request-attribute-unsupported",
                "this tag reads a server-side request attribute, and Gen3 has no equivalent: "
                "configured capture reads the browser, and a request attribute is evaluated on "
                "the server's trace. There is no path for it, so this tag does not migrate",
                blocking=True,
            )
        )
        return row

    row["source"] = "metadata"
    metadata_id = tag.get("metadataId")
    setting = capture_settings.get(metadata_id)
    if setting is None:
        row["blocked"] = True
        row["blockedReason"] = "unresolved-capture-setting"
        flags.append(
            _flag(
                "unresolved-capture-setting",
                f"metadataId {metadata_id!r} matches no `metaDataCaptureSettings` entry, so what "
                "this tag reads cannot be read back -- and a tag whose capture rule cannot be "
                "resolved looks unmappable when it may not be",
                blocking=True,
            )
        )
        return row

    row["capture"] = {
        "type": setting.get("type"),
        "capturingName": setting.get("capturingName"),
        "uniqueId": setting.get("uniqueId"),
    }
    translated = translate_capture_expression(setting.get("type"), setting.get("capturingName"))
    flags.extend(translated["flags"])
    if translated["blocked"]:
        row["blocked"] = True
        row["blockedReason"] = "capture-not-translatable"
        return row
    # The name `plan --expression` knows this tag by, whichever event property it ends up
    # reading: the generated key, never a property's that it shares.
    row["expressionKey"] = user_tag_key(tag, index)
    reused = reuse_by_capture_id.get(setting.get("uniqueId"))
    if reused:
        # The same `metaDataCaptureSettings` entry is already migrating as a captured property,
        # and capture is the raw value in both cases -- extraction and case-folding happen in
        # the pipeline, not at capture. So the tag reads the property that is already there
        # rather than adding a second capture of the same thing, which would be a second capture
        # to pay for and a second value to keep in step. A query string that property has
        # already been split, so the tag reads the parameter as it is.
        row["key"] = reused
        row["reusesCaptureOf"] = reused
    else:
        row["key"] = user_tag_key(tag, index)
        row["capturingSteps"] = translated["steps"]
        if translated.get("pipeline"):
            # The capture yields the whole query string; the tag's own statement splits the
            # parameter out before anything else reads it.
            row["queryParameter"] = translated["pipeline"]["parameter"]

    if setting.get("publicMetadata") is False:
        flags.append(
            _flag(
                "privacy-regression",
                "classic excluded this capture for visitors who signal Do-Not-Track, and Gen3 "
                "has no equivalent control -- migrated as-is the tag **will** identify those "
                "visitors too. For a user identifier that is a wider change than it is for an "
                "ordinary property, and masking is not a fix here: a masked identifier is not "
                "an identifier. The real choice is not migrating this tag",
            )
        )

    if isinstance(tag.get("cleanupRule"), str) and tag["cleanupRule"].strip():
        source = user_tag_value(row)
        extraction = cleanup_rule_entry(
            tag["cleanupRule"], source, supplied=expressions.get(row["expressionKey"])
        )
        row["extraction"] = {
            name: extraction[name]
            for name in ("expression", "expressionSource", "untranslatable")
            if name in extraction
        }
        row["pendingExpression"] = "expression" not in extraction
        flags.append(cleanup_flag(extraction))

    if row["ignoreCase"]:
        flags.append(
            _flag(
                "case-folded-after-extraction",
                "classic stored this tag in lower case, after its cleanup rule ran and whether "
                "or not the rule matched. The pipeline does the same, in the same order: it "
                "extracts first and lower-cases second",
            )
        )

    return row


def user_tag_source_field(row: Dict[str, Any]) -> Optional[str]:
    """The event property this tag reads, before any extraction."""
    if not row.get("key"):
        return None
    return f"{EVENT_PREFIX}{row['key']}"


def user_tag_value(row: Dict[str, Any]) -> Optional[str]:
    """The tag's value before extraction: the event property, or its parameter for a query string."""
    field = user_tag_source_field(row)
    if field and row.get("queryParameter"):
        return query_parameter_expression(field, row["queryParameter"])
    return field


def user_tag_branch(row: Dict[str, Any]) -> Optional[str]:
    """One `coalesce` argument: this tag's value, or null when this tag did not match.

    ⚠ The emptiness guard is not defensive tidying. A cookie that was never set captures as the
    empty string, while an unmatched selector captures as null -- both observed on one record,
    from two accessors, at the same instant. `coalesce` returns the first argument that is not
    null, so without the guard an absent cookie returns `""` and shadows every later tag that
    did match.

    The guard always tests the **captured** value, never the extracted one. Two reasons, and
    both matter: it is what classic tests -- a tag whose cleanup rule matches nothing keeps its
    raw value and does not fall through to the next tag -- and it leaves a cleanup placeholder
    appearing once in the statement rather than twice, so replacing it cannot half-succeed.
    """
    field = user_tag_source_field(row)
    if not field:
        return None
    if row.get("pendingExpression"):
        value = _cleanup_placeholder(field, str(row["cleanupRule"]))
    else:
        value = (row.get("extraction") or {}).get("expression") or user_tag_value(row)
    folded = f"lower({value})" if row.get("ignoreCase") else value
    return f'if({field} != "", {folded})'


def user_tag_statement(rows: List[Dict[str, Any]]) -> Optional[str]:
    """One application's whole user tagging, as one statement.

    One statement rather than one per tag, and that is a correctness requirement rather than
    tidiness: repeated `fieldsAdd` to the same field overwrite each other, so N processors are
    last-wins where classic is first-wins, and the migration would invert your own
    precedence without saying so. `coalesce` takes its arguments in order and returns the first
    that is not null, which is classic's rule exactly.
    """
    branches = [branch for branch in (user_tag_branch(row) for row in rows) if branch]
    if not branches:
        return None
    if len(branches) == 1:
        expression = branches[0]
    else:
        joined = ",\n    ".join(branches)
        expression = f"coalesce(\n    {joined})"
    return f"fieldsAdd {USER_TAG_FIELD} = {expression}"


def plan_user_tags(
    app: Dict[str, Any],
    *,
    capture_settings: Dict[Any, Dict[str, Any]],
    property_rows: List[Dict[str, Any]],
    drop_source_default: bool = False,
    drop_source_overrides: Optional[Dict[str, bool]] = None,
    expressions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Every `userTags` entry on one application, in the order classic returned them.

    ⚠ The order is preserved deliberately and has to stay that way. It is not decorative and it
    is not `uniqueId` order: three controlled sessions differing only in array position had the
    winner follow the position every time. Sorting these rows, or reading `userTags` into a map,
    silently picks the wrong tag for any application carrying more than one.
    """
    reuse_by_capture_id: Dict[Any, str] = {}
    for prop_row in property_rows:
        capture = prop_row.get("capture") or {}
        # A property whose pipeline rewrites its value -- an extraction, a mask -- is not
        # shared: the tag would read what the property's rules made of the value rather than
        # what was captured, and a masked identifier is not an identifier.
        rewritten = any(
            rule.get("rule") in ("cleanup", "masking") for rule in prop_row.get("pipeline") or []
        )
        if (
            not prop_row.get("blocked")
            and prop_row.get("settingsField") == CAPTURED
            and prop_row.get("key")
            and capture.get("uniqueId") is not None
            and not rewritten
        ):
            reuse_by_capture_id.setdefault(capture["uniqueId"], prop_row["key"])

    rows: List[Dict[str, Any]] = []
    for index, tag in enumerate(app.get("userTags") or []):
        if not isinstance(tag, dict):
            continue
        rows.append(
            plan_user_tag(
                tag,
                index=index,
                capture_settings=capture_settings,
                reuse_by_capture_id=reuse_by_capture_id,
                expressions=expressions,
            )
        )

    live = [row for row in rows if not row["blocked"] and row.get("key")]
    notes: List[Dict[str, Any]] = []
    if rows and not live:
        # The distinction the report has to carry: an application whose only tagging is
        # unmigratable has an unsupported outcome, not an empty one. Reporting nothing here
        # reads as "nothing to do", which is the opposite of what happened.
        notes.append(
            _flag(
                "no-user-tag-migrates",
                "every user tag on this application is blocked, so its user tagging does not "
                "migrate at all. That is an unsupported outcome, not an empty one: the "
                "application will have no user identifier until one is set another way",
                blocking=True,
            )
        )
    if live:
        notes.append(
            _flag(
                "crop-lifted",
                f"classic stored the tag cropped to {CLASSIC_USER_TAG_CROP} characters and said "
                "nothing about it; Gen3 stores it whole, and this migration keeps the longer "
                "value rather than reproducing the crop. Tags that were being truncated will "
                "now carry their full value, so anything downstream that matched the truncated "
                "form -- a filter, an alert, an export, a join -- has to be checked",
            )
        )
        notes.append(
            _flag(
                "last-action-wins-is-free",
                "across a session, the last user action carrying a tag decides the session's "
                "identifier -- on both platforms, identically. Nothing is generated for it",
            )
        )

    # The same question option C raises, and here it is sharper: a tag's
    # `event_properties.user_tag_<uniqueId>` is a key **this tool invented** to carry a value
    # into `user.identifier`. Classic never had it, nothing downstream can be reading it, and
    # it lands on every event the tag matched.
    #
    # Two exclusions, both load-bearing. A tag that **reuses a property's capture** shares that
    # property's event property, which is a real migrated property and is not this rule's to
    # remove -- the property's own row decides its fate. And a tag whose statement still carries
    # a cleanup placeholder is not sendable at all, so removing its carrier would only make the
    # refusal harder to read.
    overrides = drop_source_overrides or {}
    dropped: List[Dict[str, Any]] = []
    for row in live:
        if row.get("reusesCaptureOf"):
            continue
        if not resolve_drop_source(
            row["key"], default=drop_source_default, overrides=overrides
        ):
            continue
        dropped.append(_removal_rule(row["key"], reason=DROP_REASON_USER_TAG))
    if dropped:
        notes.append(
            _flag(
                "user-tag-carrier-dropped",
                f"the {len(dropped)} captured "
                f"{'key' if len(dropped) == 1 else 'keys'} this migration invented to carry a "
                "user tag "
                f"{'is' if len(dropped) == 1 else 'are'} removed from the event after "
                f"{USER_TAG_FIELD} has been set, so the tag leaves no event property behind. "
                "The capture-properties entry stays -- the value still has to be captured "
                "before it can be lifted; only the field is removed, and only after the "
                "statement that reads it"
            )
        )
    elif live and not drop_source_default:
        notes.append(
            _flag(
                "user-tag-carrier-kept",
                "each migrated tag leaves an `event_properties.user_tag_<uniqueId>` on every "
                "event it matched -- a key this migration invented, which classic never had "
                f"and only {USER_TAG_FIELD} reads. It can be removed in a second change, once "
                "the identifier has been verified. Keeping it is a "
                "reasonable default while verifying: it is the only place the captured value "
                "is visible if the identifier does not arrive"
            )
        )
    return {
        "tags": rows,
        "migrating": [row["index"] for row in live],
        "pendingExpression": any(row.get("pendingExpression") for row in live),
        "statement": user_tag_statement(live),
        "dropSources": dropped,
        "notes": notes,
    }

# --------------------------------------------------------------------------- artifacts


def inventory_artifact(result: InventoryResult, *, classic_host: str) -> Dict[str, Any]:
    return {
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "artifact": "inventory",
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "listedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": {"classicHost": classic_host},
        "secondsPerRequest": (
            round(result.seconds_per_request(), 3)
            if result.seconds_per_request() is not None
            else None
        ),
        "estimatedSweepSeconds": result.estimated_sweep_seconds(),
        "applications": result.entries,
        "errors": result.errors,
    }


def scan_artifact(result: ScanResult, *, classic_host: str, mode: str = "selected") -> Dict[str, Any]:
    return {
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "artifact": "scan",
        "mode": mode,
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "scannedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": {"classicHost": classic_host},
        "withProperties": [
            {
                "id": app["id"],
                "kind": app["kind"],
                "name": app["name"],
                "properties": len(app["userActionAndSessionProperties"]),
                "sessionScoped": sum(
                    1
                    for prop in app["userActionAndSessionProperties"]
                    if isinstance(prop, dict) and prop.get("storeAsSessionProperty") is True
                ),
            }
            for app in result.applications
            if app["userActionAndSessionProperties"]
        ],
        "applications": result.applications,
        "errors": result.errors,
        "warnings": result.warnings,
    }


def human_duration(seconds: Optional[int]) -> str:
    """Rounded on purpose: this is quoted to someone deciding whether to wait."""
    if seconds is None:
        return "an unknown amount of time"
    if seconds < 90:
        return f"about {max(seconds, 1)} seconds"
    return f"about {int(round(seconds / 60.0))} minutes"


def summarise_inventory(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Counts and a next step. The names stay in the artifact, for the same reason keys do."""
    per_kind: Dict[str, int] = {}
    for entry in artifact["applications"]:
        per_kind[entry["kind"]] = per_kind.get(entry["kind"], 0) + 1
    total = len(artifact["applications"])
    return {
        "command": "scan",
        "mode": "inventory",
        "applications": total,
        "applicationsByKind": per_kind,
        "estimatedSweepSeconds": artifact.get("estimatedSweepSeconds"),
        "nextStep": (
            f"{total} applications were listed. Which of them carry properties has not been "
            "checked: that is one request per application, "
            f"{human_duration(artifact.get('estimatedSweepSeconds'))} on this tenant. Ask which "
            "application(s) to migrate and re-run with --application ENTITY_ID (repeatable). If "
            "the answer is all of them, or a substantial number, say the sweep takes "
            f"{human_duration(artifact.get('estimatedSweepSeconds'))} and re-run with --all — "
            "which reports which applications carry properties, so the choice can then be made "
            "from a complete list."
        ),
        "errors": artifact["errors"],
    }


def summarise_scan(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """The summary is what a human or an agent reads. It carries counts, never values.

    Property keys, display names and capture expressions stay in the artifact on disk: they are
    your configuration, and there is no reason for them to travel through a terminal, a
    transcript or a log to be counted.
    """
    by_origin: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    by_capture_type: Dict[str, int] = {}
    session_scoped = 0
    total_properties = 0
    apps_with_properties = 0
    per_kind: Dict[str, int] = {}

    for app in artifact["applications"]:
        per_kind[app["kind"]] = per_kind.get(app["kind"], 0) + 1
        properties = app["userActionAndSessionProperties"]
        if properties:
            apps_with_properties += 1
        for prop in properties:
            if not isinstance(prop, dict):
                continue
            total_properties += 1
            origin = str(prop.get("origin") or "UNSPECIFIED")
            by_origin[origin] = by_origin.get(origin, 0) + 1
            type_name = str(prop.get("type") or "UNSPECIFIED")
            by_type[type_name] = by_type.get(type_name, 0) + 1
            if prop.get("storeAsSessionProperty") is True:
                session_scoped += 1
        for item in app["metaDataCaptureSettings"]:
            if not isinstance(item, dict):
                continue
            capture_type = str(item.get("type") or "UNSPECIFIED")
            by_capture_type[capture_type] = by_capture_type.get(capture_type, 0) + 1

    summary = {
        "command": "scan",
        "mode": artifact.get("mode", "selected"),
        "applications": len(artifact["applications"]),
        "applicationsByKind": per_kind,
        "applicationsWithProperties": apps_with_properties,
        "properties": total_properties,
        "propertiesByOrigin": by_origin,
        "propertiesByType": by_type,
        "sessionScopedProperties": session_scoped,
        "captureSettingsByType": by_capture_type,
        "errors": artifact["errors"],
        "warnings": artifact["warnings"],
    }
    if summary["mode"] in ("auto", "all"):
        summary["nextStep"] = (
            f"{apps_with_properties} of {summary['applications']} applications carry properties "
            "to migrate; the artifact lists them under withProperties, with a count each. Offer "
            "that list and migrate the ones chosen — the rest have nothing to migrate."
        )
    return summary


def write_artifact(out_dir: Path, name: str, payload: Dict[str, Any]) -> Path:
    """Returns the resolved path: an artifact whose reported location is relative is a hazard.

    The artifacts carry your configuration -- an inventory is every application name on the
    tenant -- so where they landed has to be unambiguous in the output, not relative to a
    working directory the reader has to guess at.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = (out_dir / name).resolve()
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------- the plan phase

SCHEMA_BY_KIND = {
    "web": "builtin:rum.web.capture-properties",
    "mobile": "builtin:rum.mobile.capture-properties",
}


def capture_settings_index(app: Dict[str, Any]) -> Dict[Any, Dict[str, Any]]:
    """`metadataId` on a property -> the `metaDataCaptureSettings` entry with that `uniqueId`."""
    index: Dict[Any, Dict[str, Any]] = {}
    for setting in app.get("metaDataCaptureSettings") or []:
        if isinstance(setting, dict) and setting.get("uniqueId") is not None:
            index[setting["uniqueId"]] = setting
    return index


def resolve_row2_option(
    classic_key: Any, *, default: Optional[str], overrides: Dict[str, str]
) -> Optional[str]:
    if isinstance(classic_key, str) and classic_key in overrides:
        return overrides[classic_key]
    return default


def resolve_drop_source(
    key: Any, *, default: bool, overrides: Dict[str, bool]
) -> bool:
    """Whether this key's carrier event property goes, once the rule that reads it has run.

    The override is looked up under the **classic** key for a property, because that is the
    name on the plan you are reading, and under the **generated** key for a user tag, because a
    classic tag has no key of its own. Neither namespace can shadow the other: a generated tag
    key always starts `user_tag_`.
    """
    if isinstance(key, str) and key in overrides:
        return overrides[key]
    return default


def plan_application(
    app: Dict[str, Any],
    *,
    row2_default: Optional[str],
    row2_overrides: Dict[str, str],
    drop_source_default: bool = False,
    drop_source_overrides: Optional[Dict[str, bool]] = None,
    expressions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """One scanned application -> its plan rows, with collisions resolved across the whole set."""
    capture_index = capture_settings_index(app)
    drop_overrides = drop_source_overrides or {}
    expressions = expressions or {}
    rows: List[Dict[str, Any]] = []
    for prop in app.get("userActionAndSessionProperties") or []:
        if not isinstance(prop, dict):
            continue
        rows.append(
            plan_property(
                prop,
                kind=app["kind"],
                capture_settings=capture_index,
                row2_option=resolve_row2_option(
                    prop.get("key"), default=row2_default, overrides=row2_overrides
                ),
                drop_source=resolve_drop_source(
                    prop.get("key"),
                    default=drop_source_default,
                    overrides=drop_overrides,
                ),
                expression=expressions.get(prop.get("key")),
            )
        )
    # Collisions are a property of the *set*, not of any one row, so this runs once the whole
    # application is planned -- and it mutates the rows it blocks.
    collisions = detect_key_collisions(rows)
    # After the collisions, because a tag may reuse a property's capture and a property blocked
    # by a collision has no key to reuse.
    user_tags = plan_user_tags(
        app,
        capture_settings=capture_index,
        property_rows=rows,
        drop_source_default=drop_source_default,
        drop_source_overrides=drop_overrides,
        expressions=expressions,
    )
    return {
        "id": app["id"],
        "kind": app["kind"],
        "name": app.get("name"),
        "schemaId": SCHEMA_BY_KIND.get(app["kind"]),
        "properties": rows,
        "collisions": collisions,
        "userTagsPresent": app.get("userTagsPresent", False),
        "userTags": user_tags,
    }


def settings_payload(planned_app: Dict[str, Any]) -> Dict[str, Any]:
    """The entries this application needs, ready for `apply` to merge into what is already there.

    ⚠ This is the **desired** value, not a merged one, and deliberately so. A merge computed here
    would be computed against a read taken at plan time, and `apply` may run days later against an
    object someone else has edited since. `apply` re-reads and merges against what it finds, which
    is also when the backup is taken -- a backup of a version that is no longer current is not a
    backup.
    """
    captured: List[Dict[str, Any]] = []
    declared: List[Dict[str, Any]] = []
    for row in planned_app["properties"]:
        if row["blocked"] or not row["settingsField"]:
            continue
        if row["settingsField"] == CAPTURED:
            captured.append(
                {"propertyKey": row["key"], "capturingSteps": row["capturingSteps"]}
            )
        else:
            # `caseInsensitivePropertyKey` folds the key at ingest. Classic has no equivalent
            # setting, so authoring `true` here would invent a behaviour that was never there.
            declared.append(
                {"propertyKey": row["key"], "caseInsensitivePropertyKey": False}
            )

    # A user tag that reuses a property's capture contributes no entry -- the entry is already
    # in the list above, and a second one with the same `propertyKey` is a duplicate the schema
    # rejects. Only a tag that had to capture for itself adds anything here.
    taken = {entry["propertyKey"] for entry in captured}
    for tag in planned_app.get("userTags", {}).get("tags", []):
        if tag["blocked"] or not tag["key"] or tag["reusesCaptureOf"]:
            continue
        if tag["key"] in taken:
            continue
        taken.add(tag["key"])
        captured.append(
            {"propertyKey": tag["key"], "capturingSteps": tag["capturingSteps"]}
        )

    return {
        "scope": planned_app["id"],
        "schemaId": planned_app["schemaId"],
        "desiredValue": {
            CAPTURED: captured,
            DECLARED: declared,
        },
    }


def code_change_list(planned_app: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Rows 3, 4 and row-2 option B: what has to change in your own source code."""
    changes = []
    for row in planned_app["properties"]:
        if row["blocked"] or not row["codeChange"]:
            continue
        changes.append(
            {
                "classicKey": row["classicKey"],
                "key": row["key"],
                "row": row["row"],
                "sessionScoped": row["sessionScoped"],
                "kind": row["kind"],
                "replace": _code_change_hint(row),
                # For option B the capture expression is the whole point of the entry: it says
                # what your code has to read now that nothing reads it for you.
                "classicCapture": row["capture"],
            }
        )
    return changes


def _code_change_hint(row: Dict[str, Any]) -> str:
    if row["kind"] == "mobile":
        if row["sessionScoped"]:
            return (
                "Android: SessionPropertyEventData.addSessionProperty(...) + "
                "sendSessionPropertyEvent(...). iOS: -addSessionProperty:value: + "
                "+sendSessionPropertyEvent:"
            )
        return (
            "Android: UserAction.addEventProperty(...) / EventData.addEventProperty(...) + "
            "sendEvent(...). iOS: -addEventProperty:value: + +sendEvent:"
        )
    if row["capture"]:
        # Classic captured it, so there is no call to replace: the code is new.
        return "send it with dynatrace.sendSessionPropertyEvent()"
    if row["sessionScoped"]:
        return "replace dtrum.sendSessionProperties() with dynatrace.sendSessionPropertyEvent()"
    return "replace dtrum.addActionProperties() with dynatrace.addEventModifier()"


def pipeline_change_list(planned_app: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every OpenPipeline rule the plan implies, tied to the property it serves.

    Where they live is the plan's `pipelineTarget` (a new pipeline unless `--pipeline-id` names
    an existing one); which permissions is yours to answer.
    """
    rules = []
    for row in planned_app["properties"]:
        if row["blocked"]:
            continue
        for rule in row["pipeline"]:
            entry = dict(rule)
            entry["classicKey"] = row["classicKey"]
            entry["key"] = row["key"]
            rules.append(entry)
    return rules


def blocked_list(planned_app: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One entry per property that cannot migrate, naming the *layer* that blocks it."""
    blocked = []
    for row in planned_app["properties"]:
        if not row["blocked"]:
            continue
        blocked.append(
            {
                "classicKey": row["classicKey"],
                "row": row["row"],
                "origin": row["origin"],
                "reason": row["blockedReason"],
                "layer": blocking_layer(row),
                "flags": [flag for flag in row["flags"] if flag["blocking"]],
            }
        )
    return blocked


def blocked_user_tag_list(planned_app: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One entry per user tag that cannot migrate.

    Kept beside the blocked properties rather than merged into them: a blocked property is a
    property that will not be captured, while a blocked user tag means part or all of an
    application's *identification* stops working, and whoever reads that list is deciding a
    different question.
    """
    blocked = []
    for row in planned_app.get("userTags", {}).get("tags", []):
        if not row["blocked"]:
            continue
        blocked.append(
            {
                "index": row["index"],
                "uniqueId": row["uniqueId"],
                "source": row["source"],
                "requestAttributeId": row["requestAttributeId"],
                "capture": row["capture"],
                "reason": row["blockedReason"],
                "layer": blocking_layer(row),
                "flags": [flag for flag in row["flags"] if flag["blocking"]],
            }
        )
    return blocked


def user_tag_change(planned_app: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The user-tag rule as it reads in `openpipeline-changes.json`, or `None` if there is none.

    Deliberately not part of `pipeline_change_list`. That list is one entry per property, and
    user tagging is one entry per *application* -- folding it in would make the rule look like
    it belonged to whichever property happened to sit beside it.
    """
    planned_tags = planned_app.get("userTags") or {}
    live = [
        row for row in planned_tags.get("tags", []) if not row["blocked"] and row.get("key")
    ]
    if not live:
        return None
    return {
        "rule": USER_TAG_RULE,
        "reason": "classic-user-tagging-has-no-gen3-setting",
        "table": "user.events",
        "field": USER_TAG_FIELD,
        "tags": [
            {
                "index": row["index"],
                "uniqueId": row["uniqueId"],
                "key": row["key"],
                "reusesCaptureOf": row["reusesCaptureOf"],
                "ignoreCase": row["ignoreCase"],
                "classicCleanupRule": row["cleanupRule"],
            }
            for row in live
        ],
        "statement": planned_tags.get("statement"),
        "pendingExpression": planned_tags.get("pendingExpression", False),
        # Listed here rather than folded into `tags`, because these are separate processors
        # that run after the tagging statement -- reading them beside it is how you see that
        # the order is what makes them safe.
        "dropsEventProperties": [
            rule["field"] for rule in planned_tags.get("dropSources") or []
        ],
        "notes": planned_tags.get("notes", []),
    }


def unmatched_overrides(
    applications: List[Dict[str, Any]],
    *,
    row2_overrides: Dict[str, str],
    drop_source_overrides: Dict[str, bool],
    expressions: Optional[Dict[str, str]] = None,
) -> Dict[str, List[str]]:
    """Override keys that matched nothing in this scan.

    ⚠ These used to be accepted in silence, and silence is the wrong answer: the plan comes
    back with zero processors and nothing says why. A key that names nothing is a typo or a
    fixture that no longer exists, and both are cheaper to find here than after a round trip
    to a tenant.

    Reported, never fatal. The run is still valid -- it just did not do what was asked, and
    the difference between *nothing matched your key* and *your key matched and its row was
    not eligible* is the whole diagnosis.
    """
    property_keys = set()
    tag_keys = set()
    cleanup_keys = set()
    for app in applications:
        for row in app.get("properties") or []:
            if isinstance(row.get("classicKey"), str):
                property_keys.add(row["classicKey"])
                if any(rule.get("rule") == "cleanup" for rule in row.get("pipeline") or []):
                    cleanup_keys.add(row["classicKey"])
        for tag in (app.get("userTags") or {}).get("tags") or []:
            if isinstance(tag.get("key"), str):
                tag_keys.add(tag["key"])
            if tag.get("extraction") is not None or tag.get("pendingExpression"):
                cleanup_keys.add(tag.get("expressionKey"))
    return {
        # `--row2-key` names a classic property key; a user tag has no row-2 fork to pick.
        "row2": sorted(key for key in row2_overrides if key not in property_keys),
        # `--drop-event-property-key` names either, so a key is unmatched only if it is neither.
        "dropEventProperty": sorted(
            key
            for key in drop_source_overrides
            if key not in property_keys and key not in tag_keys
        ),
        # `--expression` replaces a cleanup rule, so a key without one matched nothing it can do.
        "expression": sorted(key for key in expressions or {} if key not in cleanup_keys),
    }


NEW_PIPELINE_ID = "rum_property_migration"
# `customId` as the pipelines schema takes it -- what shows up as `user.events:<customId>` in
# `dt.openpipeline.pipelines`. A malformed one is refused here rather than by a 400 after reads.
PIPELINE_CUSTOM_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,99}$")


def pipeline_target(pipeline_id: Optional[str]) -> Dict[str, Any]:
    """Where the processors go: a new pipeline (recommended), or one you already have.

    "New or existing" used to be asked with nothing behind the second answer, and an agent that
    heard "existing" improvised a hand edit of a shared pipeline and its routing. Both answers
    now have a payload, and the recommendation is stated rather than left to whoever asks.
    """
    if not pipeline_id or not pipeline_id.strip():
        return {
            "mode": "new",
            "pipelineId": NEW_PIPELINE_ID,
            "recommended": True,
            "why": (
                "A pipeline of its own: no edit to an object another team maintains, nothing "
                "copied from one, and undone by one route removal and one delete. Built-in and "
                "default pipelines cannot be edited anyway. The cost is one write to the shared "
                "routing object."
            ),
        }
    pipeline_id = pipeline_id.strip()
    if pipeline_id == NEW_PIPELINE_ID:
        raise UsageError(
            f"--pipeline-id {NEW_PIPELINE_ID} names the pipeline this tool creates. Leave "
            "--pipeline-id out for that; it is for joining a pipeline you already have.",
            fix=[f"Re-run `plan` without --pipeline-id to create {NEW_PIPELINE_ID}."],
        )
    if not PIPELINE_CUSTOM_ID.match(pipeline_id):
        raise UsageError(
            f"--pipeline-id {pipeline_id!r} is not a pipeline customId. It is the name shown in "
            "`dt.openpipeline.pipelines` as `user.events:<customId>` -- not the base64 objectId, "
            "and not the display name.",
            fix=[
                f"Re-run `plan` without --pipeline-id to create {NEW_PIPELINE_ID} (recommended).",
                "Or re-run `plan --pipeline-id CUSTOM_ID` with the part after `user.events:` in "
                "that pipeline's `dt.openpipeline.pipelines` value.",
            ],
        )
    return {
        "mode": "existing",
        "pipelineId": pipeline_id,
        "recommended": False,
        "why": (
            f"Processors appended to the existing custom pipeline {pipeline_id!r}, and routing "
            "left alone -- so they only see the records that pipeline's own routes already send "
            "it. A record of a migrated application that another route claims, or that the "
            "default route keeps, is never touched. The pipeline belongs to whoever maintains "
            "it: they have to agree to these processors, and undo is removing exactly these "
            "processors by id. The recommendation is still a pipeline of its own: leave "
            "--pipeline-id out."
        ),
    }


def plan_artifact(
    scan: Dict[str, Any],
    *,
    row2_default: Optional[str],
    row2_overrides: Dict[str, str],
    drop_source_default: bool = False,
    drop_source_overrides: Optional[Dict[str, bool]] = None,
    scan_path: Optional[str] = None,
    pipeline_id: Optional[str] = None,
    row2_defaulted: bool = False,
    expressions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """`row2_defaulted` says `row2_default` was not asked for: every row-2 row it decides is
    marked `decision.defaulted`, so the plan can say which answers are still the user's to change."""
    target = pipeline_target(pipeline_id)
    applications = [
        plan_application(
            app,
            row2_default=row2_default,
            row2_overrides=row2_overrides,
            drop_source_default=drop_source_default,
            drop_source_overrides=drop_source_overrides,
            expressions=expressions,
        )
        for app in scan.get("applications") or []
        # An application can have no properties and still have something to migrate: user
        # tagging is configured in a different array, so filtering on the properties alone
        # would drop its tagging without ever reporting it.
        if app.get("userActionAndSessionProperties") or app.get("userTags")
    ]
    for app in applications:
        for row in app["properties"]:
            if row.get("decision"):
                row["decision"]["defaulted"] = bool(
                    row2_defaulted and row["classicKey"] not in row2_overrides
                )
    return {
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "artifact": "plan",
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "plannedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "scan": scan_path,
            "scannedAt": scan.get("scannedAt"),
            "environment": scan.get("environment"),
        },
        "row2Option": row2_default,
        "row2Defaulted": row2_defaulted,
        "row2Overrides": row2_overrides,
        "dropEventProperty": drop_source_default,
        "dropEventPropertyOverrides": drop_source_overrides or {},
        "expressionOverrides": expressions or {},
        "unmatchedOverrides": unmatched_overrides(
            applications,
            row2_overrides=row2_overrides,
            drop_source_overrides=drop_source_overrides or {},
            expressions=expressions,
        ),
        "pipelineTarget": target,
        "applications": applications,
    }


# ----------------------------------------------------------- the OpenPipeline payload

OPENPIPELINE_PIPELINES_SCHEMA = "builtin:openpipeline.user.events.pipelines"
OPENPIPELINE_ROUTING_SCHEMA = "builtin:openpipeline.user.events.routing"
OPENPIPELINE_SCOPE = "environment"

# ⚠ The OpenPipeline objects are written through the **platform** Settings API, not the classic
# one `apply` uses for captures. Measured 2026-09-30: the classic route answers
# `404 "not available in this API version. Use 3rd gen Public Settings API instead."` for these
# two schemas, while still answering `200` for `builtin:rum.web.capture-properties`. So a
# migration spans two APIs on two hosts and needs two credentials -- this is not a host switch,
# and `SETTINGS_OBJECTS` below stays classic on purpose: `apply` writes captures, and captures
# are still served there.
PLATFORM_SETTINGS_OBJECTS = "/platform/settings/v1/objects"
PLATFORM_VALIDATE_ONLY = "validate-only=true"
# The optimistic lock is **enforced**, on updates and on deletes: the same DELETE answers 400
# without it and 204 with it. The token is opaque base64 and comes from a read taken immediately
# before the write -- it is never computed, and classic v2's `schemaVersion` is not it.
PLATFORM_LOCK_PARAM = "optimistic-locking-version"

# Every ceiling the pipeline configuration enforces, checked here rather than discovered by a
# rejected request. The API reports one violation at a time, so a payload with three problems
# costs three round trips to find out about.
MAX_PROCESSORS_PER_STAGE = 1000
MAX_MATCHER_CHARS = 4096
MAX_DQL_SCRIPT_CHARS = 8192
MAX_DESCRIPTION_CHARS = 512
MIN_PROCESSOR_ID_CHARS = 4
MAX_PROCESSOR_ID_CHARS = 100
# A processor name may not sit in the reserved namespaces.
RESERVED_ID_PREFIXES = ("dt.", "dynatrace.")

# Which rules this tool writes a statement for. A promotion and a mask are assignments of a
# value this tool already knows, so they are generated complete. A query-string split is too:
# Gen2's reading of a query string is fixed code, reproduced exactly. A classic cleanup rule is
# generated where it has an exact translation -- or where you supplied the expression -- and
# otherwise listed with everything except the statement filled in.
GENERATED_RULES = (
    "query-string-split", "cleanup", "session-property-promotion", "masking", DROP_SOURCE_RULE
)
PROCESSOR_ID_STEMS = {
    "session-property-promotion": "promote",
    "masking": "mask",
    DROP_SOURCE_RULE: "drop",
    "query-string-split": "query-param",
    "cleanup": "extract",
    USER_TAG_RULE: "user-tag",
}

MASKED_VALUE = "***"


def _processor_slug(text: Any) -> str:
    cleaned = re.sub(r"[^0-9a-z]+", "-", str(text).lower()).strip("-")
    return cleaned or "property"


def processor_id(rule: str, application_id: str, key: str) -> str:
    """A processor name that is stable across runs, unique, and legal.

    Stable matters more than readable. Running this tool twice has to produce the same name, or
    the second run adds a duplicate processor beside the first instead of replacing it. The name
    ends in a short digest of what it was built from, so two long keys sharing a prefix cannot
    be truncated onto the same name.
    """
    stem = "rum-{stem}-{app}-{key}".format(
        stem=PROCESSOR_ID_STEMS.get(rule, "rule"),
        app=instrumentation_id(application_id)[:8],
        key=_processor_slug(key),
    )
    digest = hashlib.sha256(
        "\n".join([rule, application_id, key]).encode("utf-8")
    ).hexdigest()[:8]
    room = MAX_PROCESSOR_ID_CHARS - len(digest) - 1
    return f"{stem[:room]}-{digest}"


def processor_matcher(application_id: str, field: str) -> str:
    """Two conditions, and both of them earn their place.

    The field condition is what keeps an aggregation directive off events that never carried the
    property: the value copy guards itself, because copying from an absent field leaves the
    target absent, but the aggregation statement assigns a literal and would otherwise be written
    onto every event the pipeline sees.

    The application condition is what keeps one application's rule off another's events. A route
    carries everything it matches into the same pipeline, and the setting this rule replaces
    applied to a single application -- so two applications that happen to share a property name
    would otherwise be migrated as one.
    """
    return (
        f'dt.rum.instrumentation.id == "{instrumentation_id(application_id)}" '
        f"and isNotNull({field})"
    )


def rule_processor(application_id: str, rule: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One rule, as a processor you can send. `None` for a rule whose statement is yours."""
    kind = str(rule.get("rule") or "")
    key = str(rule.get("key") or "")
    if not key:
        return None
    if kind == "session-property-promotion":
        field = f"event_properties.{key}"
        script = str(rule.get("statement") or "")
        tail = (
            "then remove the event property it was read from."
            if rule.get("dropsSource")
            else "and leave the event property in place."
        )
        description = (
            f"Keep {key} on the session, aggregated as {rule.get('aggregation')}, {tail}"
        )
    elif kind == DROP_SOURCE_RULE:
        field = str(rule.get("field") or f"event_properties.{key}")
        script = str(rule.get("statement") or f"fieldsRemove {field}")
        description = (
            f"Remove {field} once it has been read. Classic gave this value one scope and it "
            "was not the event; this processor has to stay after the one that reads it."
        )
    elif kind == "masking":
        field = str(rule.get("field") or f"event_properties.{key}")
        script = f'fieldsAdd {field} = "{MASKED_VALUE}"'
        description = (
            f"Replace every captured value of {key}. This masks the property for every "
            "visitor, which is wider than the setting it replaces."
        )
    elif kind == "query-string-split":
        field = str(rule.get("field") or f"event_properties.{key}")
        script = str(rule.get("statement") or "")
        description = (
            f"Replace the query string captured as {key} with its {rule.get('parameter')!r} "
            "parameter, read as Gen2 read it: name ignoring case, value as it appears in the URL."
        )
    elif kind == "cleanup":
        field = str(rule.get("field") or f"event_properties.{key}")
        script = str(rule.get("statement") or "")
        description = (
            f"Extract from {key} what the classic cleanup rule `{rule.get('classicCleanupRule')}` "
            "extracted; a value it does not match is removed."
        )
    else:
        return None
    if not script:
        return None
    return {
        "id": processor_id(kind, application_id, key),
        "type": "dql",
        "enabled": True,
        "matcher": processor_matcher(application_id, field),
        "description": description[:MAX_DESCRIPTION_CHARS],
        "dql": {"script": script},
    }


def user_tag_matcher(application_id: str, rows: List[Dict[str, Any]]) -> Optional[str]:
    """Fire only when at least one tag actually has a value.

    ⚠ This guard is load-bearing in a way the property matchers' is not. Those copy a value, and
    copying from an absent field leaves the target absent. This one assigns the result of a
    `coalesce`, and an all-null `coalesce` assigns null -- onto `user.identifier`, a field your
    own `identifyUser()` call may already have set. Without the guard the migration
    would erase identifiers on every event that carried none of the tags, which is most of them.

    Each term is spelled out rather than leaning on three-valued logic, because `isNotNull` is
    true for the empty string and an absent cookie captures as the empty string.
    """
    terms = []
    for row in rows:
        field = user_tag_source_field(row)
        if field:
            terms.append(f'(isNotNull({field}) and {field} != "")')
    if not terms:
        return None
    return (
        f'dt.rum.instrumentation.id == "{instrumentation_id(application_id)}" '
        f"and ({' or '.join(terms)})"
    )


def user_tag_processor(
    application_id: str, planned_tags: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """One application's user tagging as the single processor it becomes, or `None`.

    One processor for the whole application, not one per tag -- see `user_tag_statement` for
    why that is the only correct shape.
    """
    live = [
        row
        for row in planned_tags.get("tags", [])
        if not row["blocked"] and row.get("key")
    ]
    if not live:
        return None
    script = planned_tags.get("statement") or user_tag_statement(live)
    matcher = user_tag_matcher(application_id, live)
    if not script or not matcher:
        return None
    count = len(live)
    description = (
        f"Set {USER_TAG_FIELD} from {count} classic user "
        f"{'tag' if count == 1 else 'tags'}. First match wins, in the classic array order."
    )
    return {
        "id": processor_id(USER_TAG_RULE, application_id, "identifier"),
        "type": "dql",
        "enabled": True,
        "matcher": matcher,
        "description": description[:MAX_DESCRIPTION_CHARS],
        "dql": {"script": script},
    }


def processor_problems(processor: Dict[str, Any]) -> List[str]:
    """What would be rejected, named before anything is sent."""
    problems: List[str] = []
    identifier = str(processor.get("id") or "")
    if not MIN_PROCESSOR_ID_CHARS <= len(identifier) <= MAX_PROCESSOR_ID_CHARS:
        problems.append(
            f"the name {identifier!r} is {len(identifier)} characters; it has to be between "
            f"{MIN_PROCESSOR_ID_CHARS} and {MAX_PROCESSOR_ID_CHARS}"
        )
    if identifier.startswith(RESERVED_ID_PREFIXES):
        problems.append(f"the name {identifier!r} is in a reserved namespace")
    matcher = str(processor.get("matcher") or "")
    if len(matcher) > MAX_MATCHER_CHARS:
        problems.append(
            f"the condition on {identifier!r} is {len(matcher)} characters, over "
            f"{MAX_MATCHER_CHARS}"
        )
    script = str((processor.get("dql") or {}).get("script") or "")
    if not script.strip():
        problems.append(f"{identifier!r} carries no statement")
    if len(script) > MAX_DQL_SCRIPT_CHARS:
        problems.append(
            f"the statement on {identifier!r} is {len(script)} characters, over "
            f"{MAX_DQL_SCRIPT_CHARS}"
        )
    if CLEANUP_PLACEHOLDER_PREFIX in script:
        # Refused here rather than at the API, because the API would take it: the placeholder is
        # a string literal as far as DQL is concerned, so a payload carrying one validates,
        # applies, and quietly writes the token itself as somebody's user identifier.
        problems.append(
            f"the statement on {identifier!r} still carries a cleanup-rule placeholder: the "
            "expression that extracts the value is yours to write"
        )
    return problems


def routing_matchers(application_ids: Iterable[str]) -> List[str]:
    """One condition per route, each covering as many applications as will fit.

    A single route is the usual answer. The split exists because the condition has a length
    limit and the number of applications does not, and a condition one character over the limit
    is refused outright rather than truncated.
    """
    conditions = [
        f'dt.rum.instrumentation.id == "{instrumentation_id(app)}"'
        for app in sorted({str(app) for app in application_ids})
    ]
    routes: List[str] = []
    current: List[str] = []
    for condition in conditions:
        candidate = current + [condition]
        if current and len(" or ".join(candidate)) > MAX_MATCHER_CHARS:
            routes.append(" or ".join(current))
            current = [condition]
        else:
            current = candidate
    if current:
        routes.append(" or ".join(current))
    return routes


def routing_entry(
    matcher: str, *, position: int, of: int, display_name: str
) -> Dict[str, Any]:
    """One entry in the routing list: which records go to a pipeline that is not the default one.

    `pipelineType` has to say `custom`, because naming a pipeline of your own is only allowed
    when the entry is not routing to a built-in one, and `description` is required -- this is
    the line someone reading the routing list sees, and the only place they can tell what an
    entry is for without opening the pipeline behind it. The entry is also where a route is
    switched on and off: the pipeline itself has no such setting.
    """
    label = display_name if of == 1 else f"{display_name} ({position} of {of})"
    return {
        "enabled": True,
        "description": label,
        "pipelineType": "custom",
        "pipelineId": "<the objectId the create step returned>",
        "matcher": matcher,
    }


def pipeline_value(
    processors: List[Dict[str, Any]], *, pipeline_id: str, display_name: str
) -> Dict[str, Any]:
    """The pipeline to create, with one processor per rule and every other stage empty.

    Empty is deliberate. Copying the other stages from a pipeline you already have looks
    harmless and is not: a copied metric extraction repeats that pipeline's metrics for every
    record this one sees, and you would be paying for the duplicate.

    The name you give the pipeline goes in `customId`, and it is the only identity field the
    object carries: there is no `id` and no `enabled` on a pipeline. `customId` is also what you
    will see in `dt.openpipeline.pipelines` on a record the pipeline handled, as
    `user.events:<customId>`, so it is worth choosing a name you would want to read there. A
    pipeline is switched on and off by the routing entry that points at it, not by the pipeline.
    """
    return {
        "customId": pipeline_id,
        "displayName": display_name,
        "metadataList": [],
        "processing": {"processors": processors},
        "dataExtraction": {"processors": []},
        "metricExtraction": {"processors": []},
        "securityContext": {"processors": []},
        "storage": {"processors": []},
    }


def openpipeline_payload(plan: Dict[str, Any]) -> Dict[str, Any]:
    """The pipeline half of the migration, as requests rather than as instructions.

    A session-scoped property that you chose to keep session-scoped without a code change is not
    finished when the capture settings are applied. Configuration-driven capture writes event
    properties and only event properties; the pipeline is what carries the value onto the
    session, and it is the only way to do that without shipping a release. So this file is part
    of the migration, not an optional extra, and it is generated rather than described: the
    inputs are the properties you planned, and the outputs are the exact bodies to send.

    Where the processors go is the plan's `pipelineTarget`: a new pipeline and a route to it by
    default, or -- with `plan --pipeline-id` -- appended to a custom pipeline you already have,
    with routing left alone. Whether you may make either change is still yours: access to a
    pipeline and access to routing are granted separately, and routing is usually the one that
    stops people.
    """
    target = plan.get("pipelineTarget") or pipeline_target(None)
    pipeline_id = target["pipelineId"]
    processors: List[Dict[str, Any]] = []
    yours: List[Dict[str, Any]] = []
    served: List[str] = []
    for app in plan["applications"]:
        # ⚠ Every removal of a carrier event property is held back and appended after all of
        # this application's other processors. Processors run in array order, so a removal that
        # sits where its property sits would delete the field before the promotion -- or before
        # the tagging statement -- had read it. Collecting them here is what makes the shared
        # case safe: one captured property can feed a promotion *and* a user tag, and only a
        # removal that runs after both is correct.
        removals: List[Dict[str, Any]] = []
        for rule in pipeline_change_list(app):
            if str(rule.get("rule") or "") == DROP_SOURCE_RULE:
                removals.append(rule)
                continue
            processor = rule_processor(app["id"], rule)
            if processor is None:
                yours.append(
                    {
                        "applicationId": app["id"],
                        "key": rule.get("key"),
                        "classicKey": rule.get("classicKey"),
                        "rule": rule.get("rule"),
                        "whatYouSupply": (
                            "a DQL expression that yields what the classic rule extracted from "
                            f"`{rule.get('field')}`, and the value unchanged where it matched "
                            "nothing"
                        ),
                        "why": rule.get("untranslatable"),
                        "source": rule.get("parameter") or rule.get("classicCleanupRule"),
                        "supplyWith": f"plan --expression {rule.get('classicKey')}=<expression>",
                        **expression_guide(rule.get("rule")),
                    }
                )
                continue
            processors.append(processor)
            served.append(app["id"])

        # User tagging is one processor for the whole application rather than one per rule, so
        # it is built from the planned tags directly instead of going through the rule list.
        planned_tags = app.get("userTags") or {}
        tag_processor = user_tag_processor(app["id"], planned_tags)
        if tag_processor is not None:
            processors.append(tag_processor)
            served.append(app["id"])
        removals.extend(planned_tags.get("dropSources") or [])
        for rule in removals:
            processor = rule_processor(app["id"], rule)
            if processor is None:
                continue
            processors.append(processor)
            served.append(app["id"])
        for row in planned_tags.get("tags", []):
            if row["blocked"] or not row.get("pendingExpression"):
                continue
            yours.append(
                {
                    "applicationId": app["id"],
                    "key": row["key"],
                    "classicKey": None,
                    "rule": USER_TAG_RULE,
                    "whatYouSupply": (
                        "a DQL expression that yields what the classic cleanup rule extracted "
                        f"from `{user_tag_value(row)}`, and the value unchanged where it matched "
                        "nothing -- the "
                        "whole application's tagging stays unsendable until it is supplied"
                    ),
                    "why": (row.get("extraction") or {}).get("untranslatable"),
                    "source": row.get("cleanupRule"),
                    "supplyWith": f"plan --expression {row.get('expressionKey')}=<expression>",
                    **expression_guide(USER_TAG_RULE),
                }
            )

    problems = [
        problem for processor in processors for problem in processor_problems(processor)
    ]
    names = [processor["id"] for processor in processors]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        problems.append(f"two processors share the name {duplicates[0]!r}")
    if len(processors) > MAX_PROCESSORS_PER_STAGE:
        problems.append(
            f"{len(processors)} processors is over the {MAX_PROCESSORS_PER_STAGE} a stage holds; "
            "split them across two pipelines"
        )

    routes = routing_matchers(served)
    display_name = "Migrated RUM properties"
    value = pipeline_value(
        processors,
        pipeline_id=pipeline_id,
        display_name=display_name,
    )
    # One object, not classic v2's array -- the platform API answers "Unexpected data!" to a list.
    create_body = {
        "schemaId": OPENPIPELINE_PIPELINES_SCHEMA,
        "scope": OPENPIPELINE_SCOPE,
        "value": value,
    }
    payload = {
        "artifact": "openpipeline-payload",
        "whatThisIsFor": (
            "Session-scoped properties you chose to keep session-scoped without a code change. "
            "Capture settings alone cannot produce a session property -- this is the step that "
            "does, so the migration of those properties is not complete until it is applied."
        ),
        "pipelineId": pipeline_id,
        "pipelineTarget": target,
        "processorCount": len(processors),
        "applicationsServed": sorted(set(served)),
        "problems": problems,
        "needsYourExpression": yours,
        "host": (
            "These two objects go to the **platform** host, not the one `apply` writes captures "
            "to. Classic answers 404 for the OpenPipeline schemas and 200 for the capture "
            "schema, so one migration needs both hosts and both credentials -- a platform token "
            "(Bearer) here, and the classic Api-Token for `apply`. The two refusals look nothing "
            "alike: the wrong token here 401s, the wrong host 404s and reads like a missing "
            "feature."
        ),
        "create": {
            "method": "POST",
            "path": PLATFORM_SETTINGS_OBJECTS,
            "auth": "Bearer -- a platform token, not the classic Api-Token",
            "validateFirst": f"{PLATFORM_SETTINGS_OBJECTS}?{PLATFORM_VALIDATE_ONLY}",
            "answers": (
                "201 with {objectId, version} on a create, 204 on a validate-only call. A 204 "
                "from the create path means validate-only was in the query string after all."
            ),
            "body": create_body,
        },
        "route": {
            "method": "PUT",
            "auth": "Bearer -- the same platform token as the create",
            "readPath": (
                f"{PLATFORM_SETTINGS_OBJECTS}?schema-id={OPENPIPELINE_ROUTING_SCHEMA}"
                f"&scope={OPENPIPELINE_SCOPE}"
            ),
            "thenReadByIdPath": f"{PLATFORM_SETTINGS_OBJECTS}/{{objectId}}",
            "writePath": (
                f"{PLATFORM_SETTINGS_OBJECTS}/{{objectId}}?{PLATFORM_LOCK_PARAM}={{version}}"
            ),
            "howToMerge": (
                "Two reads, and the second one is not optional. The list path above returns "
                "`objectId` and `version` and **no value at all**, so read the object again by "
                "its id before composing anything -- merging into the list response silently "
                "produces a document containing only your entries, and writing that back "
                "replaces every other field of a shared environment-wide object. Then put these "
                "entries at the *front* of `routingEntries` and write the whole list back. There "
                "is one routing object for the environment, so never create a second one, and "
                "order decides which route claims a record first -- an entry appended behind a "
                "broad one never runs. Each entry needs the objectId the create step returned in "
                "its `pipelineId`, and an empty one is refused with 'Must be of type setting'. "
                "The body is `{\"value\": ...}` alone: no schemaId, no scope, and no "
                "schemaVersion -- that is classic v2's field and this API does not serve it. The "
                "lock goes in the query string, from the by-id read you just did, and a write "
                "answers 200 with the **next** version rather than an objectId."
            ),
            "entries": [
                routing_entry(
                    matcher, position=index, of=len(routes), display_name=display_name
                )
                for index, matcher in enumerate(routes, start=1)
            ],
        },
        "order": [
            "Validate the create body. A malformed payload costs one round trip instead of a "
            "half-applied change.",
            "Create the pipeline. It is inert until a route points at it, so this step changes "
            "nothing on its own. Keep the objectId and the version it answers with.",
            "Read the routing object twice -- the list path for its id, then by id for its "
            "value and its current version. Keep that value; it is the undo.",
            "Put the entries at the front of routingEntries and write it back with the lock. "
            "This is the only step that touches anything shared.",
        ],
        "undo": [
            "Take this pipeline's entries out of the routing object first, so no route is left "
            "pointing at a pipeline that is about to disappear. Leave every other entry as it "
            "is now -- not as the saved value has it: another team may have changed routing "
            "since. Re-read the version immediately beforehand: the one from the original read "
            "is stale by two writes. `restore` does both steps.",
            "Then delete the pipeline object, with the lock parameter and a version read just "
            "before it -- the delete is refused with 400 without it. A successful delete "
            "answers 204, not 200.",
        ],
    }
    if target["mode"] == "existing":
        payload.update(existing_pipeline_steps(pipeline_id, processors, routes))
    return payload


def existing_pipeline_steps(
    pipeline_id: str, processors: List[Dict[str, Any]], routes: List[str]
) -> Dict[str, Any]:
    """The `--pipeline-id` variant: one pipeline update, no create, no routing write.

    Leaving routing alone is the point of choosing an existing pipeline and why it is the
    lower-risk write -- but it also means these processors only run on what that pipeline already
    receives. Their matchers still name the applications, so other traffic through the same
    pipeline is unaffected.
    """
    return {
        "create": None,
        "route": None,
        "update": {
            "method": "PUT",
            "auth": "Bearer -- a platform token, not the classic Api-Token",
            "readPath": (
                f"{PLATFORM_SETTINGS_OBJECTS}?schema-id={OPENPIPELINE_PIPELINES_SCHEMA}"
                f"&scope={OPENPIPELINE_SCOPE}"
            ),
            "thenReadByIdPath": f"{PLATFORM_SETTINGS_OBJECTS}/{{objectId}}",
            "writePath": (
                f"{PLATFORM_SETTINGS_OBJECTS}/{{objectId}}?{PLATFORM_LOCK_PARAM}={{version}}"
            ),
            "find": (
                "The list path returns objectId and version and no value, so read each object by "
                f"id until one has `value.customId == {pipeline_id!r}`. None means the id is "
                "wrong or the pipeline is built-in -- stop; do not create one under that name."
            ),
            "howToMerge": (
                "Append these processors to the **end** of `value.processing.processors` and "
                "change nothing else: no other stage, no other processor, not `customId`. The "
                "pipeline's own processors keep running first. Refuse if any of these processor "
                "ids is already there -- that is a previous run, and a second copy runs every "
                "rule twice. The body is `{\"value\": ...}` alone, with the lock from the by-id "
                "read just before."
            ),
            "processors": processors,
            "processorIds": [processor["id"] for processor in processors],
        },
        "routingCheck": (
            "Routing is not written. Read it and check that a route to this pipeline covers the "
            "migrated applications' records -- `wouldHaveRouted` is what this tool would have "
            "routed. If none does, these processors never run: say so to the user rather than "
            "adding a route by hand."
        ),
        "wouldHaveRouted": routes,
        "order": [
            "Find the pipeline by id and keep its value -- it is the record of what was there.",
            "Validate the merged value: the same PUT with `validate-only=true`.",
            "Write it with the lock, read it back, check the processor ids sit at the end.",
            "Read routing and confirm a route reaches this pipeline for the migrated "
            "applications. Write nothing there.",
        ],
        "undo": [
            "Re-read the pipeline, remove exactly the processors in `processorIds`, and write it "
            "back with a freshly read lock. Do not write the saved value back wholesale: its "
            "owner may have changed it since.",
        ],
    }


def derived_artifacts(plan: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Five views of the plan, each a file someone different acts on.

    They are views of `plan.json`, not a second source of truth: the settings payload goes to
    whoever applies configuration, the code changes to whoever owns the application's source, the
    pipeline rules and the pipeline payload to whoever owns OpenPipeline, and the blocked list to
    whoever decides what happens to a property that cannot migrate.

    The two pipeline files are not a duplicate of each other. One lists the rules against the
    properties they serve, which is what you read to decide; the other is the request bodies,
    which is what you send once you have decided.
    """
    common = {
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "plannedAt": plan["plannedAt"],
        "source": plan["source"],
    }
    return {
        "settings-payload.json": dict(
            common,
            artifact="settings-payload",
            applications=[settings_payload(app) for app in plan["applications"]],
        ),
        "code-changes.json": dict(
            common,
            artifact="code-changes",
            applications=[
                {"id": app["id"], "kind": app["kind"], "changes": code_change_list(app)}
                for app in plan["applications"]
            ],
        ),
        "openpipeline-changes.json": dict(
            common,
            artifact="openpipeline-changes",
            note=(
                "This is the list to read when you decide; `openpipeline-payload.json` is the "
                "same work as request bodies, and it already answers which applications each "
                "rule covers and what the matcher has to be. Where they go is `pipelineTarget` "
                "in plan.json: a new pipeline by default, an existing custom one with "
                "`plan --pipeline-id`. Who is allowed to make the change is not something it "
                "can answer. Promotion matchers gate on the source field, never "
                "`true`. `userTagging` is one entry per application rather than per property, "
                "because an application's tags share a single statement -- see its `notes`."
            ),
            applications=[
                {
                    "id": app["id"],
                    "kind": app["kind"],
                    "rules": pipeline_change_list(app),
                    "userTagging": user_tag_change(app),
                }
                for app in plan["applications"]
            ],
        ),
        "openpipeline-payload.json": dict(common, **openpipeline_payload(plan)),
        "blocked.json": dict(
            common,
            artifact="blocked",
            applications=[
                {
                    "id": app["id"],
                    "kind": app["kind"],
                    "blocked": blocked_list(app),
                    "blockedUserTags": blocked_user_tag_list(app),
                }
                for app in plan["applications"]
            ],
        ),
    }


def summarise_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Counts only, for the same reason `summarise_scan` carries counts only.

    Flag *names* are this tool's vocabulary rather than your configuration, so the histogram is
    safe; every flag's detail, and every key, stays in the artifacts.
    """
    by_row: Dict[str, int] = {}
    by_field: Dict[str, int] = {}
    by_flag: Dict[str, int] = {}
    total = blocked = pending = code_changes = key_changes = defaulted = 0
    pipeline_rules: Dict[str, int] = {}
    collisions = 0
    tags_total = tags_blocked = tags_pending = 0
    tags_by_reason: Dict[str, int] = {}
    apps_tagging = apps_tagging_lost = 0
    # The two answers to the carrier question, counted side by side. A report that only counted
    # the removals would make "we kept them" look like "we were not asked".
    carriers_dropped = carriers_kept = 0

    for app in plan["applications"]:
        collisions += len(app["collisions"])
        planned_tags = app.get("userTags") or {}
        tag_rows = planned_tags.get("tags", [])
        if tag_rows:
            apps_tagging += 1
        if tag_rows and not planned_tags.get("migrating"):
            apps_tagging_lost += 1
        if planned_tags.get("pendingExpression"):
            tags_pending += 1
        for tag_row in tag_rows:
            tags_total += 1
            if tag_row["blocked"]:
                tags_blocked += 1
                reason = tag_row["blockedReason"] or "unclassified"
                tags_by_reason[reason] = tags_by_reason.get(reason, 0) + 1
            for flag in tag_row["flags"]:
                by_flag[flag["flag"]] = by_flag.get(flag["flag"], 0) + 1
        for note in planned_tags.get("notes", []):
            by_flag[note["flag"]] = by_flag.get(note["flag"], 0) + 1
        for rule in planned_tags.get("dropSources") or []:
            carriers_dropped += 1
            pipeline_rules[rule["rule"]] = pipeline_rules.get(rule["rule"], 0) + 1
        for row in app["properties"]:
            total += 1
            row_name = f"row{row['row']}" if row["row"] else "unclassified"
            by_row[row_name] = by_row.get(row_name, 0) + 1
            field = row["settingsField"] or ("blocked" if row["blocked"] else "undecided")
            by_field[field] = by_field.get(field, 0) + 1
            if row["blocked"]:
                blocked += 1
            if row["decisionPending"]:
                pending += 1
            if (row.get("decision") or {}).get("defaulted") and not row["blocked"]:
                defaulted += 1
            if row["codeChange"]:
                code_changes += 1
            if row["keyChanged"]:
                key_changes += 1
            for flag in row["flags"]:
                by_flag[flag["flag"]] = by_flag.get(flag["flag"], 0) + 1
            if not row["blocked"]:
                for rule in row["pipeline"]:
                    pipeline_rules[rule["rule"]] = pipeline_rules.get(rule["rule"], 0) + 1
                if row.get("dropsEventProperty"):
                    carriers_dropped += 1
                elif any(
                    rule["rule"] == "session-property-promotion" for rule in row["pipeline"]
                ):
                    carriers_kept += 1

    summary: Dict[str, Any] = {
        "command": "plan",
        "applications": len(plan["applications"]),
        "properties": total,
        "propertiesByRow": by_row,
        "propertiesBySettingsField": by_field,
        "keysChanged": key_changes,
        "codeChanges": code_changes,
        "pipelineRulesByKind": pipeline_rules,
        "keyCollisions": collisions,
        "blocked": blocked,
        "decisionsPending": pending,
        "row2Defaulted": defaulted,
        "applicationsWithUserTagging": apps_tagging,
        "userTags": tags_total,
        "userTagsBlocked": tags_blocked,
        "userTagsBlockedByReason": tags_by_reason,
        "applicationsLosingAllUserTagging": apps_tagging_lost,
        "applicationsWithUserTagExpressionPending": tags_pending,
        "eventPropertyCarriersDropped": carriers_dropped,
        "eventPropertyCarriersKept": carriers_kept,
        "flags": by_flag,
    }
    if sum(pipeline_rules.values()) or apps_tagging:
        # Stated whenever there is pipeline work, so "which pipeline?" is answered before it is
        # asked -- and asked of the user only as "keep the recommendation?".
        target = plan.get("pipelineTarget") or pipeline_target(None)
        summary["pipelineTarget"] = {
            "mode": target["mode"],
            "pipelineId": target["pipelineId"],
            "recommended": target["recommended"],
            "why": target["why"],
        }
    # ⚠ Before anything else in the summary, because an override that matched nothing makes
    # every count below it a count of the wrong thing. A plan with zero processors and a key
    # that names nothing is one fact, not two.
    unmatched = plan.get("unmatchedOverrides") or {}
    stray = sorted(
        set(unmatched.get("row2") or [])
        | set(unmatched.get("dropEventProperty") or [])
        | set(unmatched.get("expression") or [])
    )
    if stray:
        summary["unmatchedOverrides"] = unmatched
        summary["unmatchedOverridesWarning"] = (
            f"{len(stray)} override key{'' if len(stray) == 1 else 's'} matched nothing in this "
            f"scan and {'was' if len(stray) == 1 else 'were'} ignored: "
            + ", ".join(f"`{key}`" for key in stray)
            + ". A property override is looked up under the **classic** key exactly as it "
            "appears in scan.json, and a user-tag override under the generated "
            "`user_tag_<uniqueId>` key. If the key is spelled right, the property is not in "
            "the scan -- check that the application was in scope and that the property still "
            "exists on the tenant. An --expression key also has to name a property or tag that "
            "carries a cleanup rule."
        )
    if pending:
        summary["nextStep"] = (
            f"{pending} propert{'y is' if pending == 1 else 'ies are'} `META_DATA` and "
            "session-scoped -- decision-table row 2, which this tool will not decide. Each is "
            "listed in plan.json "
            "with the three options and what each one costs. Re-run with --row2 A|B|C, or "
            "--row2-key <classic key>=A|B|C for individual ones. Until then they contribute "
            "nothing to the settings payload."
        )
    if carriers_kept:
        # The suggestion, made once and in the place that is already being read. Classic gave
        # a session-scoped property one scope; the migration gives it two, and the second one is
        # an artefact of how capture works rather than anything that was asked for.
        summary["eventPropertySuggestion"] = (
            f"{carriers_kept} promoted propert"
            f"{'y keeps' if carriers_kept == 1 else 'ies keep'} "
            "`event_properties.<key>` beside the session property the promotion writes. "
            "Classic scoped these to the session only, so the event property is new -- it is "
            "the carrier the capture had to write for the promotion to read. Removing it is "
            "one extra processor per property, appended after the promotion, and it costs "
            "nothing to leave in place. It can be removed once the promotion has been verified "
            "and nothing reads the event property -- a query, a dashboard, a segment or an "
            "alert still pointed at it stops returning."
        )
    if apps_tagging_lost:
        # Louder than a count, because this one is easy to read past: the application migrated,
        # and its users stopped being identified.
        summary["userTaggingWarning"] = (
            f"{apps_tagging_lost} application{'' if apps_tagging_lost == 1 else 's'} "
            f"{'has' if apps_tagging_lost == 1 else 'have'} user tagging that does not migrate "
            "at all -- after this migration nothing sets a user identifier for "
            f"{'it' if apps_tagging_lost == 1 else 'them'}. The reason for each tag is in "
            "blocked.json under blockedUserTags."
        )
    if tags_pending:
        summary["userTagExpressionPending"] = (
            f"{tags_pending} application{'' if tags_pending == 1 else 's'} "
            f"{'has' if tags_pending == 1 else 'have'} a user tag whose classic cleanup rule "
            "has no exact translation. The statement is written except for the extraction, "
            "and `apply` refuses the pipeline half while it is missing -- for the application's "
            "whole tagging, not just that one tag. Write the expression and re-run `plan` with "
            "`--expression KEY=<expression>`; each KEY and the reason it was not translated are "
            "in openpipeline-payload.json under needsYourExpression. Or run "
            "`apply --capture-only` and leave the pipeline half for later."
        )
    return summary


# ------------------------------------------------------------------ the apply phase

SETTINGS_OBJECTS = "/api/v2/settings/objects"
SETTINGS_SCHEMAS = "/api/v2/settings/schemas"

# The list endpoint's default field set is `objectId,value`. Ask for the rest or the
# `updateToken` is simply never there -- and a PUT without one is a silent last-writer-wins
# overwrite that nothing reports: the API takes it and answers 200.
SETTINGS_OBJECT_FIELDS = "objectId,value,updateToken,schemaVersion"


def unlocked_write_warning() -> Dict[str, Any]:
    """Recorded on a PUT sent without `updateToken`: it landed, but nothing guarded it."""
    return {
        "warning": "no-update-token",
        "detail": (
            "the tenant's read returned no updateToken, even by id, so this write was sent "
            "without optimistic-concurrency protection and could have overwritten a change "
            "made between the read and the write. Read the object back if that matters."
        ),
    }

# The two documented per-frontend ceilings. A tenant-wide ceiling also exists and is
# deliberately not checked here: it sums across every application on the tenant, so a count of
# one object could not check it honestly. When it binds, the platform rejects the write and its
# own message is what you see.
FIELD_CEILINGS = {CAPTURED: 100, DECLARED: 200}


def resolve_schema_version(client: HttpClient, schema_id: str, cache: Dict[str, str]) -> str:
    """The schema's current version, read from the tenant. Never hardcoded.

    A tenant can report a version in a shorter form than the documentation quotes -- `"1"` for
    what is written elsewhere as `1.0.0` -- and the version moves as the schema does. Every form
    would have been a plausible constant to hardcode and every one would eventually be wrong.
    Read it, echo it back.

    The call doubles as a hard-stop pre-flight: a tenant where this schema does not resolve
    fails here, before anything is written, with a message that says which schema is missing.
    """
    if schema_id in cache:
        return cache[schema_id]
    payload = client.get_json(SETTINGS_SCHEMAS, {"pageSize": "500"})
    items = payload.get("items") if isinstance(payload, dict) else None
    for item in items or []:
        if isinstance(item, dict) and item.get("schemaId") == schema_id:
            version = str(item.get("latestSchemaVersion") or "")
            if not version:
                raise ApiError(
                    0, f"{schema_id} reports no latestSchemaVersion", SETTINGS_SCHEMAS,
                    fix=FIX_UNEXPECTED,
                )
            cache[schema_id] = version
            return version
    raise ApiError(
        0,
        f"{schema_id} is not available on this tenant. The Gen3 capture-properties schema is "
        "SaaS-only; on Dynatrace Managed it never resolves, and nothing can be written.",
        SETTINGS_SCHEMAS,
        fix=[
            "Stop: this tenant cannot take the migration. Run `preflight` to confirm -- its "
            "capture-schema gate checks the same thing -- and tell the user."
        ],
    )


def read_settings_object(
    client: HttpClient, *, schema_id: str, scope: str
) -> Optional[Dict[str, Any]]:
    """The existing capture-properties object at this scope, or `None` if there is none.

    `None` is an ordinary answer: creating a classic application materialises no settings
    object, so an unmigrated application genuinely has nothing here and the write is a create.
    """
    payload = client.get_json(
        SETTINGS_OBJECTS,
        {
            "schemaIds": schema_id,
            "scopes": scope,
            "fields": SETTINGS_OBJECT_FIELDS,
            "pageSize": "100",
        },
    )
    items = payload.get("items") if isinstance(payload, dict) else None
    if not items:
        return None
    obj = items[0] if isinstance(items[0], dict) else None
    if obj is None:
        return None
    # The schema is `multiObject: false`, so one object per scope is the contract rather than
    # an assumption about this tenant's data.
    if not obj.get("updateToken") and obj.get("objectId"):
        # Defended rather than trusted: reading one object by id takes no `fields` parameter and
        # answers with everything, so it is the fallback when the list did not carry a token.
        quoted = urllib.parse.quote(str(obj["objectId"]), safe="")
        full = client.get_json(f"{SETTINGS_OBJECTS}/{quoted}")
        if isinstance(full, dict):
            obj = full
    return obj


def merge_desired_value(
    existing_value: Optional[Dict[str, Any]],
    desired_value: Dict[str, Any],
    *,
    overwrite: bool = False,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Merge the desired entries into the object the tenant already has. Never replace it.

    `multiObject: false` means this one object holds **every** Gen3 property the application
    has, migrated or hand-written. A write of only the migrated entries deletes the rest,
    silently and completely, which is the worst thing this tool could do.

    Two consequences beyond the lists themselves:

    - anything the existing object carries that this tool does not author is copied through
      untouched -- `configLessProperties` where a preview tenant already has it, a field a later
      schema version adds. A migrator that drops what it does not recognise downgrades a
      configuration it was asked to extend. It is *preserved*, never authored;
    - a key that already exists keeps the entry the tenant has, and the difference is
      reported. Overwriting it would silently rewrite a Gen3 property somebody configured
      deliberately, and there is no reason to assume the classic definition is the better one.
      `--overwrite-existing` says otherwise, per run, on the record.
    """
    creating = not existing_value
    merged = {} if creating else json.loads(json.dumps(existing_value))
    decisions: List[Dict[str, Any]] = []
    for field in (CAPTURED, DECLARED):
        current = merged.get(field)
        current = [entry for entry in current if isinstance(entry, dict)] if isinstance(current, list) else []
        index = {
            entry.get("propertyKey"): position
            for position, entry in enumerate(current)
            if entry.get("propertyKey")
        }
        for entry in desired_value.get(field) or []:
            key = entry.get("propertyKey")
            if key not in index:
                current.append(entry)
                decisions.append({"field": field, "propertyKey": key, "action": "added"})
            elif current[index[key]] == entry:
                decisions.append({"field": field, "propertyKey": key, "action": "unchanged"})
            elif overwrite:
                decisions.append(
                    {
                        "field": field,
                        "propertyKey": key,
                        "action": "replaced",
                        "previous": current[index[key]],
                    }
                )
                current[index[key]] = entry
            else:
                decisions.append(
                    {
                        "field": field,
                        "propertyKey": key,
                        "action": "kept-existing",
                        "existing": current[index[key]],
                        "desired": entry,
                        "detail": (
                            "the tenant already has this property key with a different "
                            "definition; the existing one was kept. Re-run with "
                            "--overwrite-existing to replace it."
                        ),
                    }
                )
        # On a create both lists are written even when empty -- that is the payload shape the
        # API accepts and returns unchanged. On an update a list that was absent and stays empty is
        # left absent, so that a second `apply` of the same plan compares equal to what is
        # already there and makes no request at all.
        if creating or current or field in merged:
            merged[field] = current
    return merged, decisions


def preflight_ceilings(merged_value: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The two publicly documented per-frontend ceilings, checked before the write."""
    problems = []
    for field, ceiling in FIELD_CEILINGS.items():
        count = len(merged_value.get(field) or [])
        if count > ceiling:
            problems.append(
                {
                    "problem": "ceiling-exceeded",
                    "field": field,
                    "count": count,
                    "ceiling": ceiling,
                    "detail": (
                        f"the merged object would hold {count} entries in `{field}`, and the "
                        f"documented per-frontend ceiling is {ceiling}. That ceiling can be "
                        "raised for a tenant, so this is a question to take up with Dynatrace "
                        "rather than a verdict -- but it is raised before the write, not after "
                        "a rejected one."
                    ),
                }
            )
    return problems


class ApplyRecord:
    """One application's pass through `apply`: what was read, what it merges to, what happened.

    The read and the write are separate passes over these records, so that the backup artifact
    is written after every read and before the first write. A backup that lands halfway through
    a batch is not a backup of the batch.
    """

    def __init__(self, app: Dict[str, Any], payload: Dict[str, Any]) -> None:
        self.id: str = app["id"]
        self.kind: str = app["kind"]
        self.schema_id: str = payload["schemaId"]
        self.scope: str = payload["scope"]
        self.desired: Dict[str, Any] = payload["desiredValue"]
        self.existing: Optional[Dict[str, Any]] = None
        self.merged: Optional[Dict[str, Any]] = None
        self.decisions: List[Dict[str, Any]] = []
        self.problems: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.action: str = "pending"
        self.error: Optional[Dict[str, Any]] = None

    @property
    def desired_entries(self) -> int:
        return len(self.desired.get(CAPTURED) or []) + len(self.desired.get(DECLARED) or [])

    def result(self) -> Dict[str, Any]:
        counts = {
            field: len((self.merged or {}).get(field) or []) for field in (CAPTURED, DECLARED)
        }
        by_action: Dict[str, int] = {}
        for decision in self.decisions:
            by_action[decision["action"]] = by_action.get(decision["action"], 0) + 1
        return {
            "id": self.id,
            "kind": self.kind,
            "schemaId": self.schema_id,
            "action": self.action,
            "objectId": (self.existing or {}).get("objectId"),
            "existed": self.existing is not None,
            "desiredEntries": self.desired_entries,
            "entriesByAction": by_action,
            "mergedCounts": counts,
            "entries": self.decisions,
            "problems": self.problems,
            "warnings": self.warnings,
            "error": self.error,
        }


def _api_error_entry(app_id: str, stage: str, exc: ApiError) -> Dict[str, Any]:
    return {
        "applicationId": app_id,
        "stage": stage,
        "status": exc.status,
        "message": exc.message,
        "whatToDo": exc.what_to_do,
    }


def read_current_objects(
    client: HttpClient,
    plan: Dict[str, Any],
    *,
    only_ids: Optional[Iterable[str]] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> Tuple[List[ApplyRecord], List[Dict[str, Any]]]:
    """Pass one: read what is already there, for every application the plan covers."""
    report = progress or (lambda _message: None)
    wanted = {value.strip() for value in only_ids} if only_ids else None
    applications = [
        app for app in plan.get("applications") or [] if wanted is None or app["id"] in wanted
    ]
    if wanted:
        known = {app["id"] for app in plan.get("applications") or []}
        missing = sorted(wanted - known)
        if missing:
            raise UsageError(
                "--application named "
                + ", ".join(missing)
                + ", which the plan does not cover. `apply` writes only what `plan` planned.",
                fix=[
                    "Name only applications plan.json lists under `applications`, or leave "
                    "--application out.",
                    "Or plan them first: `scan --application ID`, then `plan`, then `apply`.",
                ],
            )

    records: List[ApplyRecord] = []
    errors: List[Dict[str, Any]] = []
    for position, app in enumerate(applications, start=1):
        record = ApplyRecord(app, settings_payload(app))
        records.append(record)
        if record.desired_entries == 0:
            # Nothing to write means nothing to read: an application whose every property is
            # blocked or undecided should not cost a request, and should not appear in a backup
            # as though it had been touched.
            record.action = "nothing-to-write"
            continue
        report(f"reading settings {position}/{len(applications)}: {record.id}")
        try:
            record.existing = read_settings_object(
                client, schema_id=record.schema_id, scope=record.scope
            )
        except ApiError as exc:
            record.action = "failed"
            record.error = _api_error_entry(record.id, "read", exc)
            errors.append(record.error)
    return records, errors


def backup_artifact(
    records: Iterable[ApplyRecord],
    *,
    classic_host: str,
    plan_path: Optional[str] = None,
    pipeline: Optional[PipelineRecord] = None,
) -> Dict[str, Any]:
    """The pre-existing settings objects, written before the first write of the run.

    `existed: false` is as load-bearing as the value: it tells `restore` that the object did not
    exist before this run, so undoing the run means deleting it, not writing an empty one back.
    """
    return {
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "artifact": "backup",
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "capturedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": {"classicHost": classic_host},
        "source": {"plan": plan_path},
        "applications": [
            {
                "id": record.id,
                "kind": record.kind,
                "schemaId": record.schema_id,
                "scope": record.scope,
                "existed": record.existing is not None,
                "objectId": (record.existing or {}).get("objectId"),
                "schemaVersion": (record.existing or {}).get("schemaVersion"),
                "updateToken": (record.existing or {}).get("updateToken"),
                "value": (record.existing or {}).get("value"),
            }
            # Only what is about to be written: a record that failed its read, has nothing to
            # write, or merged to exactly what is already there is not going to be touched, and
            # a backup that lists it invites a restore of an object this run never changed.
            for record in records
            if record.action == "pending"
        ],
        "pipeline": pipeline.backup() if pipeline is not None and pipeline.pending() else None,
    }


def merge_changes(records: Iterable[ApplyRecord], *, overwrite: bool = False) -> None:
    """Pass two: merge, and check the ceilings. Makes no request and writes nothing.

    It is a pass of its own because the backup, which lands between this and the write, has to
    know which records will actually be written. Deciding that inside the write pass means the
    backup is taken before anything has been merged -- so a run where every entry is already
    present, which is what a second `apply` of the same plan is, still leaves a backup file
    behind: a snapshot of the already-migrated object, timestamped *later* than the real one and
    therefore the one a hurried restore would reach for. Found by running it twice, not by
    reasoning about it.
    """
    for record in records:
        if record.action != "pending":
            continue
        existing_value = (record.existing or {}).get("value")
        existing_value = existing_value if isinstance(existing_value, dict) else None
        record.merged, record.decisions = merge_desired_value(
            existing_value, record.desired, overwrite=overwrite
        )
        record.problems = preflight_ceilings(record.merged)
        if record.problems:
            record.action = "refused"
        elif existing_value is not None and record.merged == existing_value:
            # Every desired entry was already there, byte for byte. Re-running `apply` after a
            # successful one costs reads and nothing else -- and backs nothing up.
            record.action = "unchanged"


def write_changes(
    client: HttpClient,
    records: Iterable[ApplyRecord],
    *,
    dry_run: bool = False,
    progress: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Pass three: write what pass two merged. Every record is handled in isolation."""
    report = progress or (lambda _message: None)
    errors: List[Dict[str, Any]] = []
    pending = [r for r in records if r.action == "pending"]
    versions: Dict[str, str] = {}

    for position, record in enumerate(pending, start=1):
        if dry_run:
            record.action = "dry-run"
            continue

        try:
            if record.existing is None:
                version = resolve_schema_version(client, record.schema_id, versions)
                report(f"creating settings {position}/{len(pending)}: {record.id}")
                client.send_json(
                    "POST",
                    SETTINGS_OBJECTS,
                    [
                        {
                            "schemaId": record.schema_id,
                            "schemaVersion": version,
                            "scope": record.scope,
                            "value": record.merged,
                        }
                    ],
                )
                record.action = "created"
            else:
                object_id = str(record.existing.get("objectId") or "")
                if not object_id:
                    raise ApiError(
                        0, "the existing settings object reports no objectId", SETTINGS_OBJECTS,
                        fix=FIX_UNEXPECTED,
                    )
                body: Dict[str, Any] = {"value": record.merged}
                if record.existing.get("schemaVersion"):
                    body["schemaVersion"] = record.existing["schemaVersion"]
                token = record.existing.get("updateToken")
                if token:
                    # Optional at the API level, and omitting it degrades to a blind overwrite
                    # that answers 200. Always sent; nothing would remind us.
                    body["updateToken"] = token
                else:
                    record.warnings.append(unlocked_write_warning())
                report(f"updating settings {position}/{len(pending)}: {record.id}")
                client.send_json(
                    "PUT", f"{SETTINGS_OBJECTS}/{urllib.parse.quote(object_id, safe='')}", body
                )
                record.action = "updated"
        except ApiError as exc:
            record.action = "failed"
            record.error = _api_error_entry(record.id, "write", exc)
            errors.append(record.error)
    return errors


# --------------------------------------------------------------- the pipeline half

PLATFORM_VALIDATE_PARAMS = {"validate-only": "true"}


def platform_client(
    settings: Dict[str, str], *, timeout: float = DEFAULT_TIMEOUT
) -> Tuple[HttpClient, str]:
    """A client for the platform Settings API, and the host it talks to.

    The pipeline and its route are not served by Environment API v2 at all, so this is a second
    client on a second host with a second credential -- not a substitute for the classic one.
    """
    base, token = settings.get("DT_PLATFORM_BASE"), settings.get("DT_PLATFORM_TOKEN")
    if not base or not token:
        missing = "DT_PLATFORM_BASE" if not base else "DT_PLATFORM_TOKEN"
        raise CredentialError(
            f"{missing} is not set. The pipeline and its route are written through the platform "
            f"Settings API with a platform token carrying {' + '.join(PLATFORM_SCOPES)}. To "
            "write the capture settings alone, re-run with --capture-only: the migration is then "
            f"half-applied until --pipeline-only has run too. {NOT_SET_HINT}",
            fix=set_fix(
                missing,
                PLATFORM_EXAMPLE if missing == "DT_PLATFORM_BASE"
                else f"a platform token with {' + '.join(PLATFORM_SCOPES)}",
            ) + [
                "Or write the capture settings alone with `--capture-only`, and the pipeline "
                "later with `--pipeline-only`."
            ],
        )
    url = normalise_base(base, expect_apps_host=True, label="DT_PLATFORM_BASE")
    return HttpClient(url, f"Bearer {token}", timeout=timeout), urllib.parse.urlsplit(url).netloc


def _object_path(object_id: str) -> str:
    return f"{PLATFORM_SETTINGS_OBJECTS}/{urllib.parse.quote(object_id, safe='')}"


def _locked(version: Any, *, validate: bool = False) -> Dict[str, str]:
    params = {PLATFORM_LOCK_PARAM: str(version or "")}
    if validate:
        params.update(PLATFORM_VALIDATE_PARAMS)
    return params


def list_platform_objects(client: HttpClient, schema_id: str) -> List[Dict[str, Any]]:
    """Every object of a schema, as ids and versions: the list path carries no value at all."""
    page = client.get_json(
        PLATFORM_SETTINGS_OBJECTS, {"schema-id": schema_id, "scope": OPENPIPELINE_SCOPE}
    ) or {}
    items = [
        item for item in page.get("items") or [] if isinstance(item, dict) and item.get("objectId")
    ]
    # One page holds everything: the default page size is the largest integer, and no page key
    # comes back. A count larger than the page would mean that changed, and finding by customId
    # on half a list creates a second pipeline under the same name.
    if int(page.get("totalCount") or 0) > len(items):
        raise ApiError(
            0,
            f"the list answered {len(items)} of {page.get('totalCount')} objects; this tool does "
            "not page it. Nothing was written.",
            PLATFORM_SETTINGS_OBJECTS,
            fix=[
                "Write the capture settings alone with `--capture-only`, and report the "
                "message: the platform Settings API started paging, and finding the pipeline on "
                "half a list would create a second one."
            ],
        )
    return items


def environment_of(host: str) -> str:
    """`abc12345.live.dynatrace.com` and `abc12345.apps.dynatrace.com` -> `abc12345`."""
    return host.split(".", 1)[0].lower()


def refuse_other_platform(platform_host: str, *, host: str) -> None:
    """The platform host belongs to the tenant the classic one names, or nothing is written."""
    if environment_of(platform_host) != environment_of(host):
        raise UsageError(
            f"DT_PLATFORM_BASE names {platform_host} and DT_CLASSIC_BASE names {host} -- two "
            "different environments. Both halves of a migration go to one environment. Check "
            "both settings.",
            fix=[
                f"Set DT_PLATFORM_BASE to https://{environment_of(host)}.apps.dynatrace.com if "
                f"{host} is the tenant the user confirmed.",
                f"Or set DT_CLASSIC_BASE to the classic host of {environment_of(platform_host)}, "
                "and start over there with `preflight`.",
            ],
        )


def read_platform_object(client: HttpClient, object_id: str) -> Dict[str, Any]:
    """The one read an update may be composed from: by id, with its value and its lock."""
    found = client.get_json(_object_path(object_id))
    if not isinstance(found, dict) or not isinstance(found.get("value"), dict):
        raise ApiError(
            0, "the by-id read returned no value", _object_path(object_id), fix=FIX_UNEXPECTED
        )
    return found


def find_pipeline(
    client: HttpClient, custom_id: str, *, seen: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """The pipeline with this customId. `seen` collects every customId read on the way."""
    for item in list_platform_objects(client, OPENPIPELINE_PIPELINES_SCHEMA):
        found = read_platform_object(client, str(item["objectId"]))
        if seen is not None:
            seen.append(str(found["value"].get("customId") or ""))
        if found["value"].get("customId") == custom_id:
            return found
    return None


def read_routing(client: HttpClient) -> Dict[str, Any]:
    """The environment's one routing object. Anything other than exactly one is refused."""
    items = list_platform_objects(client, OPENPIPELINE_ROUTING_SCHEMA)
    if len(items) != 1:
        raise ApiError(
            0,
            f"expected one routing object for the environment and found {len(items)}; this tool "
            "neither creates a second one nor guesses which one counts. Nothing was written.",
            PLATFORM_SETTINGS_OBJECTS,
            fix=[
                "Write the capture settings alone with `--capture-only`, and add the route by "
                "hand: openpipeline-payload.json carries the pipeline under `create` and its "
                "routing entries under `route`.",
                "Or join a pipeline that is already routed: re-run `plan --pipeline-id "
                "CUSTOM_ID`, which leaves routing alone.",
            ],
        )
    return read_platform_object(client, str(items[0]["objectId"]))


def processors_in(value: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return list(((value or {}).get("processing") or {}).get("processors") or [])


def with_processors(value: Dict[str, Any], processors: List[Dict[str, Any]]) -> Dict[str, Any]:
    """`value` with its processing stage replaced, and every other field as it was read."""
    return {**value, "processing": {**(value.get("processing") or {}), "processors": processors}}


def routing_with(
    value: Dict[str, Any], object_id: str, entries: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """`value` with every entry for `object_id` replaced by `entries`, at the front.

    Every other entry stays exactly as it was read, in its order. First match wins, so an entry
    behind a broad one never runs -- the front is the only place these can go.
    """
    others = [
        entry for entry in value.get("routingEntries") or [] if entry.get("pipelineId") != object_id
    ]
    return {**value, "routingEntries": [*entries, *others]}


def _carries(theirs: Any, ours: Dict[str, Any]) -> bool:
    """Every field we send, as we send it. The API may add defaults of its own on the way in."""
    return isinstance(theirs, dict) and all(theirs.get(key) == value for key, value in ours.items())


def _same_list(theirs: List[Any], ours: List[Dict[str, Any]]) -> bool:
    return len(theirs) == len(ours) and all(_carries(t, o) for t, o in zip(theirs, ours))


def _routed_as_planned(
    value: Dict[str, Any], object_id: str, entries: List[Dict[str, Any]]
) -> bool:
    current = value.get("routingEntries") or []
    head, tail = current[: len(entries)], current[len(entries):]
    return _same_list(head, entries) and not any(e.get("pipelineId") == object_id for e in tail)


def _validated_put(
    client: HttpClient, object_id: str, value: Dict[str, Any], version: Any, *, dry_run: bool
) -> None:
    """Validate, then write, with the lock from the read just before. A dry run only validates."""
    path = _object_path(object_id)
    client.send_json("PUT", path, {"value": value}, _locked(version, validate=True))
    if not dry_run:
        client.send_json("PUT", path, {"value": value}, _locked(version))


class PipelineRecord:
    """The pipeline half of one `apply` run: what the payload wants, and what the tenant has.

    Same three passes as the capture half -- read, decide, write -- so the backup taken between
    them covers the pipeline and the routing object as they were before this run touched either.
    """

    def __init__(self, payload: Dict[str, Any], *, host: str) -> None:
        target = payload["pipelineTarget"]
        self.host = host
        self.mode: str = target["mode"]
        self.custom_id: str = target["pipelineId"]
        existing = self.mode == "existing"
        self.processors: List[Dict[str, Any]] = (
            payload["update"]["processors"]
            if existing
            else payload["create"]["body"]["value"]["processing"]["processors"]
        )
        self.create_body: Optional[Dict[str, Any]] = None if existing else payload["create"]["body"]
        self.entries: List[Dict[str, Any]] = [] if existing else payload["route"]["entries"]
        self.applications: List[str] = list(payload.get("applicationsServed") or [])
        self.pending_expressions = len(payload.get("needsYourExpression") or [])
        self.pipeline: Optional[Dict[str, Any]] = None
        self.routing: Optional[Dict[str, Any]] = None
        self.object_id: Optional[str] = None
        self.pipeline_action = "pending"
        self.routing_action = "not-written" if existing else "pending"
        self.routes_to_pipeline: Optional[int] = None
        self.warnings: List[str] = []
        self.error: Optional[Dict[str, Any]] = None
        self.client: Optional[HttpClient] = None
        self.seen: List[str] = []

    @property
    def processor_ids(self) -> List[str]:
        return [processor["id"] for processor in self.processors]

    def entries_for(self, object_id: str) -> List[Dict[str, Any]]:
        return [dict(entry, pipelineId=object_id) for entry in self.entries]

    def pending(self) -> bool:
        return "pending" in (self.pipeline_action, self.routing_action)

    def backup(self) -> Dict[str, Any]:
        """What `restore` needs to undo this half, and the record of what was there."""
        routing = None
        if self.mode == "new" and self.routing:
            routing = {"objectId": self.routing.get("objectId"), "value": self.routing.get("value")}
        return {
            "platformHost": self.host,
            "mode": self.mode,
            "customId": self.custom_id,
            "existed": self.pipeline is not None,
            "objectId": self.object_id,
            "value": (self.pipeline or {}).get("value"),
            "processorIds": self.processor_ids,
            "routing": routing,
        }

    def result(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "pipelineId": self.custom_id,
            "platformHost": self.host,
            "objectId": self.object_id,
            "processors": len(self.processors),
            "processorIds": self.processor_ids,
            "applications": self.applications,
            "pipelineAction": self.pipeline_action,
            "routingAction": self.routing_action,
            "routesToPipeline": self.routes_to_pipeline,
            "needsYourExpression": self.pending_expressions,
            "warnings": self.warnings,
            "error": self.error,
        }


def read_pipeline_state(
    client: HttpClient,
    record: PipelineRecord,
    *,
    progress: Optional[Callable[[str], None]] = None,
) -> None:
    """Pass one for the pipeline half. A failed read stops the run before anything is written.

    The capture half isolates a failed application and carries on, because each application is
    its own object. This half cannot: a capture write without the pipeline that reads it is a
    half-applied migration, so the choice to write only captures is the user's, by
    --capture-only, never this tool's after a 403.
    """
    report = progress or (lambda _message: None)
    report(f"reading the pipelines on {record.host}")
    try:
        record.pipeline = find_pipeline(client, record.custom_id, seen=record.seen)
        report("reading the routing object")
        record.routing = read_routing(client)
    except ApiError as exc:
        raise ApiError(
            exc.status,
            f"the pipeline half could not be read on {record.host}: {exc.message}. Nothing was "
            "written. Fix the platform token or host, or re-run with --capture-only to write the "
            "capture settings alone.",
            exc.url_path,
            fix=exc.what_to_do + ["Or write the capture settings alone with `apply --capture-only`."],
        ) from exc
    if record.pipeline is not None:
        record.object_id = str(record.pipeline.get("objectId") or "")
    decide_pipeline(record)


def decide_pipeline(record: PipelineRecord) -> None:
    """Pass two: pending or unchanged, for the pipeline and for the route. Makes no request."""
    current = (record.pipeline or {}).get("value") or {}
    routing = (record.routing or {}).get("value") or {}
    if record.mode == "existing":
        if record.pipeline is None:
            raise UsageError(
                f"no custom pipeline has customId {record.custom_id!r} on {record.host}. It is "
                "the name `dt.openpipeline.pipelines` shows as `user.events:<customId>`. Built-in "
                "and default pipelines cannot be joined. Nothing was written.",
                fix=[
                    "Re-run `plan --pipeline-id CUSTOM_ID` with one of the custom pipelines on "
                    f"{record.host}: {', '.join(sorted(filter(None, record.seen))) or 'there are none'}.",
                    f"Or re-run `plan` without --pipeline-id to create {NEW_PIPELINE_ID} "
                    "(recommended).",
                ],
            )
        theirs = processors_in(current)
        ids = set(record.processor_ids)
        present = [processor for processor in theirs if processor.get("id") in ids]
        if not present:
            record.pipeline_action = "pending"
        elif _same_list(theirs[len(theirs) - len(present):], record.processors):
            record.pipeline_action = "unchanged"
        else:
            raise UsageError(
                f"{record.custom_id!r} already carries {len(present)} of these processors, but not "
                "as this plan has them -- an earlier run of a different plan. Undo it with "
                "`restore --backup <that run's backup>` first. Nothing was written.",
                fix=[
                    "Run `restore --pipeline-only --backup backup-<stamp>.json` with the backup "
                    "of the run that added them, then `apply` again.",
                    f"Or re-run `plan` without --pipeline-id to create {NEW_PIPELINE_ID} "
                    "instead.",
                ],
            )
        record.routes_to_pipeline = sum(
            1
            for entry in routing.get("routingEntries") or []
            if entry.get("pipelineId") == record.object_id and entry.get("enabled", True)
        )
        if not record.routes_to_pipeline:
            record.warnings.append(
                f"No enabled route sends records to {record.custom_id!r}, so these processors "
                "never run. This tool does not write routing for a pipeline it did not create: "
                "its owner has to route the migrated applications to it."
            )
        return

    if record.pipeline is None:
        record.pipeline_action = "pending"
    elif _same_list(processors_in(current), record.processors):
        record.pipeline_action = "unchanged"
    else:
        record.pipeline_action = "pending"
    if record.object_id and _routed_as_planned(
        routing, record.object_id, record.entries_for(record.object_id)
    ):
        record.routing_action = "unchanged"
    else:
        record.routing_action = "pending"


def write_pipeline(
    client: HttpClient,
    record: PipelineRecord,
    *,
    dry_run: bool = False,
    progress: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Pass three. Every write is validated first and carries a lock read immediately before."""
    if not record.pending():
        return []
    report = progress or (lambda _message: None)
    try:
        if record.mode == "existing":
            _write_existing_pipeline(client, record, dry_run=dry_run, report=report)
        else:
            _write_new_pipeline(client, record, dry_run=dry_run, report=report)
    except ApiError as exc:
        record.error = {"stage": "pipeline", **exc.as_dict()}
        if record.pipeline_action == "pending":
            record.pipeline_action = "failed"
        if record.routing_action == "pending":
            record.routing_action = "failed"
        return [record.error]
    return []


def pipeline_next_step(pipeline: Dict[str, Any], *, command: str) -> str:
    """What a failed pipeline half left behind, and how to finish or undo it."""
    written = {
        action for action in (pipeline["pipelineAction"], pipeline["routingAction"])
        if action not in ("failed", "pending", "unchanged", "not-written", "absent")
    }
    remedy = " ".join((pipeline["error"] or {}).get("whatToDo") or [])
    state = (
        f"The pipeline half failed part-way: pipeline {pipeline['pipelineAction']}, route "
        f"{pipeline['routingAction']}."
    )
    if command == "apply":
        left = (
            " The pipeline exists and nothing routes to it yet, so it processes nothing."
            if pipeline["pipelineAction"] == "created" and pipeline["routingAction"] == "failed"
            else ""
        )
        return (
            f"{state}{left} {remedy} Then re-run `apply`: it writes only what is still missing. "
            "Or undo the run with `restore`."
            if written else f"{state} {remedy} Then re-run `apply`."
        )
    return (
        f"{state} {remedy} Then re-run `restore` with the same --backup: it reads afresh and "
        "does only what is left."
    )


def _write_new_pipeline(
    client: HttpClient, record: PipelineRecord, *, dry_run: bool, report: Callable[[str], None]
) -> None:
    if record.pipeline_action == "pending":
        if record.pipeline is None:
            report(f"creating pipeline {record.custom_id}")
            client.send_json(
                "POST", PLATFORM_SETTINGS_OBJECTS, record.create_body, PLATFORM_VALIDATE_PARAMS
            )
            if dry_run:
                record.pipeline_action = "dry-run"
            else:
                created = client.send_json("POST", PLATFORM_SETTINGS_OBJECTS, record.create_body)
                record.object_id = str((created or {}).get("objectId") or "")
                if not record.object_id:
                    raise ApiError(
                        0, "the pipeline create answered without an objectId",
                        PLATFORM_SETTINGS_OBJECTS,
                        fix=[
                    "Re-run `apply`: it finds the pipeline by its customId and writes only what "
                    "is still missing.",
                    "Or undo this run with `restore`.",
                ],
                    )
                record.pipeline_action = "created"
        else:
            report(f"updating pipeline {record.custom_id}")
            fresh = read_platform_object(client, str(record.object_id))
            value = with_processors(fresh["value"], record.processors)
            _validated_put(client, str(record.object_id), value, fresh.get("version"), dry_run=dry_run)
            record.pipeline_action = "dry-run" if dry_run else "updated"

    if record.routing_action != "pending":
        return
    if not record.object_id:
        # A dry run of a create: there is no objectId to point a route at, and the routing
        # write is refused without one, so there is nothing it could validate either.
        record.routing_action = "dry-run"
        return
    report("routing the migrated applications to it")
    routing_id = str((record.routing or {}).get("objectId") or "")
    fresh = read_platform_object(client, routing_id)
    entries = record.entries_for(record.object_id)
    value = routing_with(fresh["value"], record.object_id, entries)
    _validated_put(client, routing_id, value, fresh.get("version"), dry_run=dry_run)
    if dry_run:
        record.routing_action = "dry-run"
        return
    back = read_platform_object(client, routing_id)
    if not _routed_as_planned(back["value"], record.object_id, entries):
        raise ApiError(
            0, "the routing object read back without these entries at the front",
            _object_path(routing_id),
            fix=[
                "Re-run `apply`: it rewrites the route. If it fails the same way, something else "
                "writes the routing object at the same time -- undo with `restore` and retry "
                "later."
            ],
        )
    record.routing_action = "updated"


def _write_existing_pipeline(
    client: HttpClient, record: PipelineRecord, *, dry_run: bool, report: Callable[[str], None]
) -> None:
    report(f"appending {len(record.processors)} processor(s) to pipeline {record.custom_id}")
    object_id = str(record.object_id)
    fresh = read_platform_object(client, object_id)
    theirs = processors_in(fresh["value"])
    ids = set(record.processor_ids)
    if any(processor.get("id") in ids for processor in theirs):
        raise ApiError(
            0, "the pipeline changed between the read and the write: it now carries some of "
            "these processors", _object_path(object_id),
            fix=[
                "Re-run `apply`: it reads the pipeline afresh, and says so if those processors "
                "came from a different plan."
            ],
        )
    value = with_processors(fresh["value"], theirs + record.processors)
    _validated_put(client, object_id, value, fresh.get("version"), dry_run=dry_run)
    if dry_run:
        record.pipeline_action = "dry-run"
        return
    back = processors_in(read_platform_object(client, object_id)["value"])
    if not _same_list(back[len(back) - len(record.processors):], record.processors):
        raise ApiError(
            0, "the pipeline read back without these processors at the end", _object_path(object_id),
            fix=[
                "Re-run `apply`. If it fails the same way, undo with `restore --pipeline-only` and "
                "report the message."
            ],
        )
    record.pipeline_action = "updated"


def apply_artifact(
    records: Iterable[ApplyRecord],
    *,
    plan: Dict[str, Any],
    classic_host: str,
    dry_run: bool,
    overwrite: bool,
    plan_path: Optional[str] = None,
    backup_path: Optional[str] = None,
    pipeline: Optional[PipelineRecord] = None,
    halves: Tuple[str, ...] = ("capture", "pipeline"),
) -> Dict[str, Any]:
    return {
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "artifact": "apply",
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "appliedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dryRun": dry_run,
        "overwriteExisting": overwrite,
        "environment": {"classicHost": classic_host},
        "source": {"plan": plan_path, "plannedAt": plan.get("plannedAt")},
        "backup": backup_path,
        "halves": list(halves),
        "applications": [record.result() for record in records],
        "pipeline": pipeline.result() if pipeline is not None else None,
    }


def summarise_apply(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Counts and action names only -- no keys, no capture expressions, same rule as the rest."""
    by_action: Dict[str, int] = {}
    entries: Dict[str, int] = {}
    problems = warnings = 0
    for app in artifact["applications"]:
        by_action[app["action"]] = by_action.get(app["action"], 0) + 1
        for action, count in app["entriesByAction"].items():
            entries[action] = entries.get(action, 0) + count
        problems += len(app["problems"])
        warnings += len(app["warnings"])

    summary: Dict[str, Any] = {
        "command": "apply",
        "dryRun": artifact["dryRun"],
        "applications": len(artifact["applications"]),
        "applicationsByAction": by_action,
        "entriesByAction": entries,
        "problems": problems,
        "warnings": warnings,
    }
    pipeline = artifact.get("pipeline")
    if pipeline:
        summary["pipeline"] = {
            key: pipeline[key]
            for key in (
                "mode", "pipelineId", "platformHost", "processors", "pipelineAction",
                "routingAction", "routesToPipeline",
            )
        }
        summary["warnings"] += len(pipeline["warnings"])
        summary["pipelineWarnings"] = pipeline["warnings"]
        if pipeline["error"]:
            summary["problems"] += 1
            summary["pipelineError"] = pipeline["error"]
    halves = artifact.get("halves") or ["capture", "pipeline"]
    if len(halves) == 1:
        ran, remaining = halves[0], "pipeline" if halves == ["capture"] else "capture"
        summary["remainingHalf"] = remaining
        summary["halfApplied"] = (
            f"Only the {HALF_IN_WORDS[ran]} {'were' if ran == 'capture' else 'was'} written. The "
            f"migration is half-applied until the {HALF_IN_WORDS[remaining]} from the same plan "
            f"{'are' if remaining == 'capture' else 'is'} written too: captures without the "
            "pipeline lose what the pipeline carries onto the session, and the pipeline without "
            "captures has nothing to read."
        )
    if entries.get("kept-existing"):
        summary["nextStep"] = (
            f"{entries['kept-existing']} propert"
            f"{'y' if entries['kept-existing'] == 1 else 'ies'} already existed on the tenant "
            "with a different definition and were left alone. Both definitions are in "
            "apply.json. Re-run with --overwrite-existing only if you want the classic "
            "definition instead."
        )
    if pipeline and pipeline["error"]:
        step = pipeline_next_step(pipeline, command="apply")
        summary["nextStep"] = f"{step} {summary['nextStep']}" if "nextStep" in summary else step
    return summary


# ------------------------------------------------------------------ the verify phase

VERIFY_WINDOW = "-24h"
RUM_SOURCE_FILTER = 'filter dt.openpipeline.source == "rumagent"'

# The agent configuration a tenant serves compiles each capturing step into one accessor
# string, type tag first, in configured order. A `JSON_PARSER` step is the bare tag; every other
# tag carries the capture value; a blank value is skipped entirely, which makes the served chain
# *shorter* than the configured one.
ACCESSOR_TAGS = {
    "COOKIE_ACCESSOR": "c",
    "DOM_ATTRIBUTE_ACCESSOR": "a",
    "JSON_PARSER": "j",
    "PROPERTY_ACCESSOR": "p",
    "QUERY_SELECTOR": "q",
}


def instrumentation_id(application_id: str) -> str:
    """`APPLICATION-<HEX>` -> `<hex>`. A lexical transform, with no query and no traffic.

    It matters here for the same reason it matters to the pipeline rules: an application that
    has never received an event must still be addressable in a query, so the id is derived from
    the entity id rather than looked up in data that may not exist yet.
    """
    _, _, body = application_id.partition("-")
    return (body or application_id).lower()


def session_scope_lines(application_id: str) -> List[str]:
    """How `user.sessions` names one of your applications -- which is not how `user.events` does.

    The session table carries no instrumentation id. What names the application there is
    `dt.smartscape.frontend`, an **array** of frontend ids: a session that visited two of your
    applications lists both, and is counted once for each. Those ids are not the ids you
    configure with and cannot be derived from them, so the query resolves them through
    Smartscape instead of guessing, and narrows that lookup to the one application first.

    Comparing the array against a quoted id looks equivalent and is not: its elements are
    Smartscape ids rather than strings, so the comparison matches nothing, reports no error, and
    returns a count of zero -- which reads exactly like a property that never arrived.

    Matching the configured id exactly is also what keeps a mobile application out of a web
    application's results, since one id is a suffix of the other.

    These queries need `storage:smartscape:read` alongside the storage scopes.
    """
    return [
        "| expand dt.smartscape.frontend",
        f'| lookup [ smartscapeNodes "FRONTEND" | filter id_classic == "{application_id}" '
        '| fields id ], sourceField: dt.smartscape.frontend, lookupField: id',
        "| filter isNotNull(lookup.id)",
    ]


def expected_accessors(capturing_steps: Optional[List[Dict[str, Any]]]) -> List[str]:
    """The accessor chain the agent should be served, derived from the steps that were written."""
    accessors: List[str] = []
    for step in capturing_steps or []:
        tag = ACCESSOR_TAGS.get(str(step.get("captureType")))
        if tag is None:
            continue
        if tag == "j":
            accessors.append(tag)
            continue
        value = step.get("captureValue")
        if isinstance(value, str) and value.strip():
            accessors.append(tag + value)
    return accessors


def _entries_by_key(value: Optional[Dict[str, Any]], field: str) -> Dict[str, Dict[str, Any]]:
    entries = (value or {}).get(field)
    return {
        entry["propertyKey"]: entry
        for entry in entries or []
        if isinstance(entry, dict) and entry.get("propertyKey")
    }


def _check(name: str, status: str, detail: str, **extra: Any) -> Dict[str, Any]:
    return {"check": name, "status": status, "detail": detail, **extra}


def verify_checks(
    desired: Dict[str, Any],
    current: Optional[Dict[str, Any]],
    *,
    backup_value: Optional[Dict[str, Any]] = None,
    backed_up: bool = False,
    blocked_keys: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    """The configuration read-back -- the only immediate, unambiguous verification there is.

    One check earns the whole layer: that the entries which were there *before* are still there.
    A migration that replaced the object instead of merging into it passes every other check in
    this list, because everything it was asked to write is present.
    """
    if current is None:
        return [
            _check(
                "object-present",
                "fail",
                "the application has no capture-properties object at all. Either `apply` never "
                "ran for it, or it ran against a different tenant.",
            )
        ]

    checks = [_check("object-present", "pass", "the settings object is there.")]

    missing: List[Dict[str, str]] = []
    differing: List[Dict[str, Any]] = []
    compared = 0
    for field in (CAPTURED, DECLARED):
        live = _entries_by_key(current, field)
        for entry in desired.get(field) or []:
            key = entry.get("propertyKey")
            if key not in live:
                missing.append({"field": field, "propertyKey": key})
            else:
                compared += 1
                if live[key] != entry:
                    differing.append({"field": field, "propertyKey": key, "onTenant": live[key]})

    checks.append(
        _check(
            "planned-entries-present",
            "fail" if missing else "pass",
            "every planned property key is on the tenant."
            if not missing
            else f"{len(missing)} planned key(s) are not on the tenant.",
            missing=missing,
        )
    )
    if missing and not compared:
        # Nothing of the plan is on the tenant, so there is nothing to compare and "every
        # planned entry matches" would be a reassuring sentence about entries that are not
        # there. A check with no input has not passed -- the same rule the backup check follows.
        checks.append(
            _check(
                "planned-entries-match",
                "skipped",
                "none of the planned entries are on the tenant, so there was nothing to compare "
                "them against. `planned-entries-present` is the check to read.",
                differing=[],
            )
        )
    else:
        checks.append(
            _check(
                "planned-entries-match",
                "fail" if differing else "pass",
                "every planned entry matches what was planned, step for step."
                if not differing
                else (
                    f"{len(differing)} entr(y/ies) differ from the plan. A conflict `apply` "
                    "reported as `kept-existing` is the expected cause and is not a defect -- "
                    "check apply.json before treating this as one."
                ),
                differing=differing,
            )
        )

    if not backed_up:
        checks.append(
            _check(
                "pre-existing-entries-survived",
                "skipped",
                "no backup artifact was given, so what the object held before this migration is "
                "unknown -- and the merge is exactly what that check would prove. Point "
                "--backup at the backup-<stamp>.json the applying run wrote.",
            )
        )
    else:
        lost: List[Dict[str, str]] = []
        for field in (CAPTURED, DECLARED):
            live = _entries_by_key(current, field)
            for key in _entries_by_key(backup_value, field):
                if key not in live:
                    lost.append({"field": field, "propertyKey": key})
        checks.append(
            _check(
                "pre-existing-entries-survived",
                "fail" if lost else "pass",
                "every property the object held before the migration is still there."
                if not lost
                else (
                    f"{len(lost)} propert(y/ies) that existed before the migration are gone. "
                    "That is a replace where a merge was intended, and the object holds one "
                    "object per application, so nothing else recorded them."
                ),
                lost=lost,
            )
        )

        dropped = [
            field
            for field in (backup_value or {})
            if field not in (CAPTURED, DECLARED) and field not in current
        ]
        checks.append(
            _check(
                "unauthored-fields-preserved",
                "fail" if dropped else "pass",
                "fields this tool does not author are unchanged."
                if not dropped
                else (
                    f"{len(dropped)} field(s) the object carried are gone. This tool authors two "
                    "lists and copies everything else through; anything else it dropped, it "
                    "downgraded."
                ),
                dropped=sorted(dropped),
            )
        )

    blocked_present = sorted(
        {
            key
            for key in blocked_keys
            if key in _entries_by_key(current, CAPTURED) or key in _entries_by_key(current, DECLARED)
        }
    )
    checks.append(
        _check(
            "blocked-properties-absent",
            "fail" if blocked_present else "pass",
            "no property the plan blocked was written."
            if not blocked_present
            else (
                f"{len(blocked_present)} blocked propert(y/ies) are on the tenant. A property "
                "reported as unmigratable and then written is the worst of both reports."
            ),
            present=blocked_present,
        )
    )
    return checks


def layer2_expectations(desired: Dict[str, Any]) -> Dict[str, Any]:
    """What the agent should be told, so the manual layer-2 check has something to compare to.

    One fact makes this worth emitting rather than describing: only `capturedEventProperties`
    reaches the agent, so an API-only migration produces no `metadataConfig` at all -- which
    reads exactly like a failed migration to anyone checking by hand.
    """
    entries = [
        {
            "propertyKey": entry.get("propertyKey"),
            "accessors": expected_accessors(entry.get("capturingSteps")),
            "steps": len(entry.get("capturingSteps") or []),
        }
        for entry in desired.get(CAPTURED) or []
    ]
    notes = [
        "Accessors are HTML-encoded whole, and `'` becomes `&#39` with no trailing semicolon. "
        "Decode before comparing, or every quoted selector reads as a mismatch.",
        "A blank captureValue is skipped, so a served chain shorter than `steps` is expected "
        "wherever a step has no value to read -- and a real defect anywhere else.",
    ]
    if not entries:
        notes.append(
            "No metadataConfig at all is the correct result here: nothing was written to "
            "capturedEventProperties, and the mapper never reads the API-reported list."
        )
    return {
        "expectMetadataConfig": bool(entries),
        "entries": entries,
        "notes": notes,
    }


def user_tag_queries(
    application_id: str, planned_tags: Optional[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Whether the migrated tagging is actually setting an identifier. Emitted, never run.

    ⚠ Two things decide the shape of these, and neither is obvious from the outside.

    They count `characteristics.has_user_identifier` rather than `user.identifier`. The value is
    in the sensitive fieldset, and the refusal to show it is **silent** -- a working migration
    and an unreadable field come back byte-identical, both null, `SUCCEEDED`, no warning. The
    characteristic is not in that fieldset, reads with the ordinary table scopes, and is true
    exactly when a value is set. Only the length check has to touch the value itself, and it
    says so.

    And they ask `user.events`, not `user.sessions`. The session table declares no
    characteristic for the identifier at all, so the same question there has nothing to count
    that is not the sensitive value -- the session-level check is not written cautiously, it is
    unbuildable.
    """
    tags = [
        row
        for row in (planned_tags or {}).get("tags", [])
        if not row["blocked"] and row.get("key")
    ]
    if not tags:
        return []
    iid = instrumentation_id(application_id)
    # ⚠ Both of the first two queries select on the carrier event property, and a migration
    # that removes the carrier removes the thing they select on. Where a carrier is gone the
    # query has to stop pretending it can see which events a tag matched: `filter <source>`
    # would match nothing and read as "no tag ever fired", and `filter not (<source>)` would
    # match everything and quietly compare the wrong population.
    dropped = {
        rule.get("key") for rule in (planned_tags or {}).get("dropSources") or []
    }
    visible = [row for row in tags if row["key"] not in dropped]
    fields = [user_tag_source_field(row) for row in visible]
    any_source = (
        " or ".join(f'(isNotNull({field}) and {field} != "")' for field in fields)
        if fields
        else None
    )
    if not dropped:
        carrier_note = ""
    elif fields:
        carrier_note = (
            f"\n\n⚠ {len(dropped)} of this application's "
            f"{len(tags)} tags have their carrier event property removed by the pipeline, so "
            "this count covers only the ones that keep it. The rest are invisible to a "
            "carrier-based check by construction."
        )
    else:
        carrier_note = (
            "\n\n⚠ Every carrier event property on this application is removed by the "
            "pipeline, so no query can tell an event a tag matched from one it did not. This "
            "check is the weaker, whole-application form. If you want the precise one, take "
            "it **before** you add the removal processors -- they are the last processors in "
            "the pipeline and can be added in a second write."
        )
    tagged_filter = [f"| filter {any_source}"] if any_source else []
    untagged_filter = [f"| filter not ({any_source})"] if any_source else []
    # An identifier the pipeline set carries no `is_api_reported`; one your own identifyUser()
    # call set carries `true`. That is what tells a migrated identifier from a pre-existing one
    # on the same record, and both checks below turn on it.
    return [
        {
            "name": "user-identifier-set-where-a-tag-matched",
            "table": "user.events",
            "expect": (
                "`identified` equal to `tagged` on every row, and `fromMigration` accounting "
                "for the ones your own code was not already setting. Each row is one pipeline "
                "combination; if yours is missing from `dt.openpipeline.pipelines` entirely, "
                "read the routing object before anything else -- a pipeline nothing routes to "
                "does nothing, and the routing object is shared, so an entry you added can be "
                "removed by the next thing that writes it. A shortfall with the pipeline "
                "present points at a disabled processor or a statement that still carries a "
                "placeholder."
            ) + carrier_note,
            "query": "\n".join(
                [
                    f"fetch user.events, from:{VERIFY_WINDOW}",
                    f"| {RUM_SOURCE_FILTER}",
                    f'| filter dt.rum.instrumentation.id == "{iid}"',
                    *tagged_filter,
                    "| summarize tagged = count(), "
                    "identified = countIf(characteristics.has_user_identifier == true), "
                    "fromMigration = countIf(characteristics.has_user_identifier == true "
                    "and isNull(characteristics.is_api_reported)), "
                    "by: { dt.openpipeline.pipelines }",
                ]
            ),
        },
        {
            "name": "identifiers-you-set-yourself-survive",
            "table": "user.events",
            "expect": (
                "`yourOwn` unchanged from before the migration. These are the events no tag "
                "matched, which the tagging processor must not touch -- and the matcher's "
                "emptiness guard is the only thing keeping it off them. If this was non-zero "
                "before and is zero now, the processor is firing where it should not and "
                "assigning null over identifiers your own identifyUser() call set: disable the "
                "route before reading anything else. If your application never calls "
                "identifyUser(), zero is expected and this query tells you nothing. Take the "
                "`before` number while the pipeline is still unrouted -- afterwards there is "
                "nothing to compare against."
            ) + carrier_note,
            "query": "\n".join(
                [
                    f"fetch user.events, from:{VERIFY_WINDOW}",
                    f"| {RUM_SOURCE_FILTER}",
                    f'| filter dt.rum.instrumentation.id == "{iid}"',
                    *untagged_filter,
                    "| summarize events = count(), "
                    "yourOwn = countIf(characteristics.is_api_reported == true)",
                ]
            ),
        },
        {
            "name": "user-identifier-values-longer-than-classic-kept",
            "table": "user.events",
            "expect": (
                f"`longer` is however many of your tags exceed {CLASSIC_USER_TAG_CROP} "
                "characters, and zero is a perfectly good answer. This is not a failure either "
                f"way: classic cropped at {CLASSIC_USER_TAG_CROP} and Gen3 does not, and this "
                "migration keeps the longer value. Run it to find out whether anything "
                "downstream -- a filter, an alert, an export, a join -- was matching the "
                "cropped form and will now stop.\n\n"
                "⚠ Unlike the two checks above, this one reads `user.identifier` itself, which "
                "is in the sensitive fieldset. Without "
                '`ALLOW storage:fieldsets:read WHERE storage:fieldset-name = '
                '"builtin-sensitive-user-events-and-sessions"` the field reads null for every '
                "record and both counts come back zero, with no error and no warning. That "
                "grant is a policy on a group, so re-minting a token does not supply it. If "
                "the first query showed identifiers arriving and this one shows none, that is "
                "what you are looking at -- not a failed migration."
            ),
            "query": "\n".join(
                [
                    f"fetch user.events, from:{VERIFY_WINDOW}",
                    f"| {RUM_SOURCE_FILTER}",
                    f'| filter dt.rum.instrumentation.id == "{iid}"',
                    "| filter isNotNull(user.identifier)",
                    "| summarize identified = count(), "
                    f"longer = countIf(stringLength(user.identifier) > {CLASSIC_USER_TAG_CROP})",
                ]
            ),
        },
    ]


def layer4_queries(
    application_id: str,
    *,
    desired: Dict[str, Any],
    session_keys: Iterable[str] = (),
    promoted_keys: Iterable[str] = (),
    cast_keys: Iterable[str] = (),
    dropped_keys: Iterable[str] = (),
    user_tags: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """The Grail checks, templated on this application's keys. Emitted, never run.

    Layer 4 needs traffic, so it is delayed confirmation and never a pass/fail gate -- which is
    why these are written out to run once traffic has caught up, rather than executed here and
    reported as a verdict.

    Every query carries the `rumagent` source filter. Synthetic monitors write to the same
    bucket and can outnumber real sessions there many times over, and they carry none of these
    fields, so an unfiltered coverage query reads as a failed migration.
    """
    iid = instrumentation_id(application_id)
    scope = f'filter dt.rum.instrumentation.id == "{iid}"'
    session_scope = session_scope_lines(application_id)
    queries: List[Dict[str, Any]] = [
        {
            "name": "control-are-any-events-arriving",
            "table": "user.events",
            "expect": (
                "non-zero. If this is zero, every query below is zero for the same reason -- no "
                "traffic, or a missing fieldset policy -- and none of them says anything about "
                "the migration."
            ),
            "query": "\n".join(
                [
                    f"fetch user.events, from:{VERIFY_WINDOW}",
                    f"| {RUM_SOURCE_FILTER}",
                    f"| {scope}",
                    "| summarize events = count()",
                ]
            ),
        }
    ]

    for entry in desired.get(CAPTURED) or []:
        key = entry.get("propertyKey")
        queries.append(
            {
                "name": f"captured-property-arriving::{key}",
                "table": "user.events",
                "propertyKey": key,
                "expect": (
                    "non-zero once traffic has arrived on a tag version that supports it. "
                    "The group by `dt.openpipeline.pipelines` is deliberate: it is what tells a "
                    "record that never reached your pipeline from one the pipeline handled "
                    "wrongly. If your pipeline is not in the list at all, read the routing "
                    "object before anything else -- a pipeline nothing routes to does nothing, "
                    "and the routing object is shared, so an entry you added can be removed by "
                    "the next thing that writes it."
                ),
                "query": "\n".join(
                    [
                        f"fetch user.events, from:{VERIFY_WINDOW}",
                        f"| {RUM_SOURCE_FILTER}",
                        f"| {scope}",
                        f'| filter isNotNull(event_properties.{key}) and event_properties.{key} != ""',
                        "| summarize events = count(), by: { dt.openpipeline.pipelines }",
                    ]
                ),
            }
        )

    for entry in desired.get(DECLARED) or []:
        key = entry.get("propertyKey")
        queries.append(
            {
                "name": f"api-reported-property-arriving::{key}",
                "table": "user.events",
                "propertyKey": key,
                "expect": (
                    "zero until your code change ships -- an allow-list entry permits a property, "
                    "it does not produce one. Zero here is only a defect once the reporting "
                    "code is live."
                ),
                "query": "\n".join(
                    [
                        f"fetch user.events, from:{VERIFY_WINDOW}",
                        f"| {RUM_SOURCE_FILTER}",
                        f"| {scope}",
                        f'| filter isNotNull(event_properties.{key}) and event_properties.{key} != ""',
                        "| summarize events = count()",
                    ]
                ),
            }
        )

    # What to expect from a session property depends on what puts it there. A key you report
    # through the API arrives when your code does; a key promoted by a pipeline rule arrives with
    # the next session. Saying "non-zero" for both would have you read a migration that is only
    # waiting on a release as a broken one.
    declared_keys = {entry.get("propertyKey") for entry in desired.get(DECLARED) or []}
    for key in session_keys:
        if key in promoted_keys:
            expect = (
                "non-zero once a session has ended that carried the property: the pipeline rule "
                "promotes the captured value into the session. No code change is involved, so a "
                "lasting zero here points at the rule or at the capture, not at a release."
            )
        elif key in declared_keys:
            expect = (
                "zero until your code change ships. The allow-list entry permits the property; "
                "your dynatrace.sendSessionPropertyEvent() call is what produces it. Non-zero "
                "once that code is live and a session has ended."
            )
        else:
            expect = "non-zero once the property is being reported and a session has ended."
        queries.append(
            {
                "name": f"session-property-arriving::{key}",
                "table": "user.sessions",
                "propertyKey": key,
                "expect": (
                    expect + " Test the property itself rather than "
                    "characteristics.has_session_properties: that characteristic can be set by "
                    "an aggregation directive alone, so it can be true for a session that "
                    "carries no session property at all."
                ),
                "query": "\n".join(
                    [
                        f"fetch user.sessions, from:{VERIFY_WINDOW}",
                        f"| {RUM_SOURCE_FILTER}",
                        *session_scope,
                        f"| filter isNotNull(session_properties.{key})",
                        "| summarize sessions = count()",
                    ]
                ),
            }
        )
    # ⚠ Both of the checks below read the source field, and a promotion that drops its carrier
    # leaves nothing to read. Their gated forms are not cosmetic variants: run the source form
    # against a dropped key and `isNull(event_properties.<key>)` is true on every record, so a
    # correctly gated rule reports every one of its own events as an orphan directive.
    for key in promoted_keys:
        if key in dropped_keys:
            queries.append(
                {
                    "name": f"promotion-directive-without-a-value::{key}",
                    "table": "user.events",
                    "propertyKey": key,
                    "expect": (
                        "**zero**. This migration removes the carrier `event_properties."
                        f"{key}` after the promotion has read it, so the gate check and the "
                        "cast check collapse into this one: every event carrying the "
                        "aggregation directive should also carry the value. A non-zero count "
                        "has two possible causes and they cannot be told apart from here -- "
                        "the rule's matcher is ungated and is stamping the directive onto "
                        "events that never carried the property, or the value is being cast "
                        "and the cast is failing. Read the processor's matcher first; it is "
                        "the cheaper of the two to check."
                    ),
                    "query": "\n".join(
                        [
                            f"fetch user.events, from:{VERIFY_WINDOW}",
                            f"| {RUM_SOURCE_FILTER}",
                            f"| {scope}",
                            f"| filter isNotNull(session_properties_aggregation.{key})",
                            f"| filter isNull(session_properties.{key})",
                            "| summarize directivesWithoutAValue = count()",
                        ]
                    ),
                }
            )
            continue
        queries.append(
            {
                "name": f"promotion-matcher-is-gated::{key}",
                "table": "user.events",
                "propertyKey": key,
                "expect": (
                    "**zero**. A non-zero count means the promotion rule's matcher is ungated and "
                    "is writing an aggregation directive onto every event of the application, "
                    "including the ones that never carried the property. Narrow the rule's "
                    "matcher until this returns nothing."
                ),
                "query": "\n".join(
                    [
                        f"fetch user.events, from:{VERIFY_WINDOW}",
                        f"| {RUM_SOURCE_FILTER}",
                        f"| {scope}",
                        f"| filter isNull(event_properties.{key})",
                        f"| filter isNotNull(session_properties_aggregation.{key})",
                        "| summarize orphanDirectives = count()",
                    ]
                ),
            }
        )
    for key in cast_keys:
        if key in dropped_keys:
            # Already covered: with the carrier gone, a failed cast *is* a directive without a
            # value, and emitting a second query that filters on the removed field would count
            # zero events and read as a pass.
            continue
        queries.append(
            {
                "name": f"promoted-value-survives-the-cast::{key}",
                "table": "user.events",
                "propertyKey": key,
                "expect": (
                    "`notNumeric` **zero**, with `events` above zero. This property is typed as a "
                    "number in the classic configuration, so the promotion casts it -- and a "
                    "captured value that is not a number cannot be cast. Every event this counts "
                    "carried the property and lost it on the way to the session, which also means "
                    "the aggregation strategy has nothing to work with there. Check what the "
                    "capture is actually reading before you rely on the aggregate."
                ),
                "query": "\n".join(
                    [
                        f"fetch user.events, from:{VERIFY_WINDOW}",
                        f"| {RUM_SOURCE_FILTER}",
                        f"| {scope}",
                        f"| filter isNotNull(event_properties.{key})",
                        "| summarize events = count(), "
                        f"notNumeric = countIf(isNull(session_properties.{key}))",
                    ]
                ),
            }
        )

    queries.append(
        {
            "name": "rejected-by-the-ingest-allowlist",
            "table": "user.events",
            "expect": (
                "empty. Any row names a full prefixed key that was rejected on ingest, which "
                "tells `not sent` apart from `sent and rejected` -- the most informative check "
                "here. Use it while migrating; it is a diagnostic field, not something to "
                "alert on."
            ),
            "query": "\n".join(
                [
                    f"fetch user.events, from:{VERIFY_WINDOW}",
                    f"| {RUM_SOURCE_FILTER}",
                    f"| {scope}",
                    "| filter isNotNull(dt.support.dropped_custom_properties)",
                    "| fields timestamp, dt.support.dropped_custom_properties",
                    "| limit 20",
                ]
            ),
        }
    )
    queries.extend(user_tag_queries(application_id, user_tags))
    return queries


def queries_document(artifact: Dict[str, Any]) -> str:
    """The layer-4 queries as a file someone can paste from, one block per query."""
    lines = [
        "// Layer-4 verification queries, generated by " + TOOL_NAME + " " + TOOL_VERSION,
        "// Layer 4 needs traffic: it is delayed confirmation, never a pass/fail gate.",
        "// Each block is built from your own property keys; read one before you run it.",
        "// Running these needs a platform token with " + ", ".join(DQL_SCOPES) + ".",
        "// Those are permissions, not only token scopes. A refusal answers",
        "// NOT_AUTHORIZED_FOR_TABLE and names the scope it wanted -- and it names it the same",
        "// way whether the scope is absent from the token or from what the user that token",
        "// belongs to is granted. A token never carries more than its user is permitted, so a",
        "// query that still fails with a freshly minted token is a permission to grant, not a",
        "// token to mint again.",
        "// Your user also needs the fieldset policy",
        "//   " + DQL_FIELDSET_POLICY,
        "// which is granted to a group rather than minted into a token. The two fail",
        "// differently, which is worth knowing before you read an empty result as a failed",
        "// migration. A table your token has no scope for fails outright, with",
        "// NOT_AUTHORIZED_FOR_TABLE, and the error names the table and the scope it wanted.",
        "// A missing fieldset policy is the quiet one: the sensitive RUM fields come back as",
        "// nulls, no error, and a filtered query simply finds nothing. Run the control query",
        "// first -- it filters on none of them, so it separates the two from a migration that",
        "// did not work.",
    ]
    for app in artifact["applications"]:
        lines.append("")
        lines.append(f"// ===== {app['id']} =====")
        for query in app["layer4"]:
            lines.append("")
            lines.append(f"// {query['name']}")
            lines.append(f"// expect: {query['expect']}")
            lines.append(query["query"])
    return "\n".join(lines) + "\n"


def write_text_artifact(out_dir: Path, name: str, text: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = (out_dir / name).resolve()
    path.write_text(text, encoding="utf-8")
    return path


def latest_backup(out_dir: Path) -> Optional[Path]:
    """The most recent `backup-<stamp>.json` in the out-dir, by name.

    The names are UTC stamps in a sortable format, so the newest sorts last -- and `AN` is what
    makes this safe to guess at: backups are never overwritten, so the file this picks is a real
    record of some run rather than a rewritten one.
    """
    backups = sorted(out_dir.glob("backup-*.json"))
    return backups[-1] if backups else None


def load_backup_artifact(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise UsageError(f"no backup artifact at {path}.", fix=FIX_FOREIGN_BACKUP)
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"{path} could not be read as JSON: {exc}", fix=FIX_FOREIGN_BACKUP) from exc
    if not isinstance(artifact, dict) or artifact.get("artifact") != "backup":
        raise UsageError(
            f"{path} is not a backup artifact -- it carries {artifact.get('artifact')!r} rather "
            "than 'backup'.",
            fix=FIX_FOREIGN_BACKUP,
        )
    return artifact


def verify_applications(
    client: HttpClient,
    plan: Dict[str, Any],
    *,
    backup: Optional[Dict[str, Any]] = None,
    only_ids: Optional[Iterable[str]] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Read every application back and check it. Reads only -- `verify` never writes."""
    report = progress or (lambda _message: None)
    wanted = {value.strip() for value in only_ids} if only_ids else None
    applications = [
        app for app in plan.get("applications") or [] if wanted is None or app["id"] in wanted
    ]
    if wanted:
        missing = sorted(wanted - {app["id"] for app in plan.get("applications") or []})
        if missing:
            raise UsageError(
                "--application named "
                + ", ".join(missing)
                + ", which the plan does not cover.",
                fix=["Name only applications plan.json lists under `applications`, or leave "
                     "--application out."],
            )

    backed_up = {
        entry["id"]: entry.get("value")
        for entry in (backup or {}).get("applications") or []
        if isinstance(entry, dict) and entry.get("id")
    }

    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for position, app in enumerate(applications, start=1):
        payload = settings_payload(app)
        desired = payload["desiredValue"]
        blocked = [row["key"] for row in app["properties"] if row["blocked"]]
        # Two different lists. A session-scoped property lands in `session_properties.*`
        # whichever way it gets there, so it is worth querying `user.sessions` for; only a
        # promoted one has a pipeline rule whose matcher could have been left ungated.
        session_keys = [
            row["key"] for row in app["properties"] if not row["blocked"] and row.get("sessionScoped")
        ]
        promoted_keys = [
            row["key"] for row in app["properties"] if not row["blocked"] and row.get("pipeline")
        ]
        # The promotion casts whenever the classic type is numeric, and a value that will not
        # parse is dropped silently. That is worth its own check, because it looks exactly like
        # a capture that never fired.
        cast_keys = [
            row["key"]
            for row in app["properties"]
            if not row["blocked"]
            and any(rule.get("cast") for rule in row.get("pipeline") or [])
        ]
        # A key whose carrier the pipeline removes cannot be checked through the carrier. The
        # queries that would have read `event_properties.<key>` are replaced rather than left
        # to return nothing and read as a pass.
        dropped_keys = {
            row["key"]
            for row in app["properties"]
            if not row["blocked"] and row.get("dropsEventProperty")
        }
        entry: Dict[str, Any] = {
            "id": app["id"],
            "kind": app["kind"],
            "schemaId": payload["schemaId"],
            "scope": payload["scope"],
            "objectId": None,
            "status": "failed",
            "counts": {},
            "checks": [],
            "layer2": layer2_expectations(desired),
            "layer4": layer4_queries(
                app["id"],
                desired=desired,
                session_keys=session_keys,
                promoted_keys=promoted_keys,
                cast_keys=cast_keys,
                dropped_keys=dropped_keys,
                user_tags=app.get("userTags"),
            ),
            "error": None,
        }
        report(f"verifying {position}/{len(applications)}: {app['id']}")
        try:
            current = read_settings_object(
                client, schema_id=payload["schemaId"], scope=payload["scope"]
            )
        except ApiError as exc:
            entry["error"] = _api_error_entry(app["id"], "read", exc)
            errors.append(entry["error"])
            results.append(entry)
            continue

        value = (current or {}).get("value")
        value = value if isinstance(value, dict) else None
        entry["objectId"] = (current or {}).get("objectId")
        entry["counts"] = {
            field: len((value or {}).get(field) or []) for field in (CAPTURED, DECLARED)
        }
        entry["checks"] = verify_checks(
            desired,
            value,
            backup_value=backed_up.get(app["id"]),
            backed_up=app["id"] in backed_up,
            blocked_keys=blocked,
        )
        failed = [check for check in entry["checks"] if check["status"] == "fail"]
        skipped = [check for check in entry["checks"] if check["status"] == "skipped"]
        entry["status"] = "failed" if failed else "incomplete" if skipped else "verified"
        results.append(entry)
    return results, errors


def verify_artifact(
    results: List[Dict[str, Any]],
    *,
    classic_host: str,
    plan_path: Optional[str] = None,
    backup_path: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "artifact": "verify",
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "verifiedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": {"classicHost": classic_host},
        "source": {"plan": plan_path, "backup": backup_path},
        "layers": {
            "1": "configuration read-back -- checked here, and the pass/fail gate",
            "2": "agent configuration -- expectations emitted, the fetch is manual",
            "3": "browser-side evaluation -- a check to run in the browser, not automated here",
            "4": "Grail data -- queries emitted, needs traffic, never an immediate verdict",
        },
        "applications": results,
    }


def summarise_verify(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Counts and check *names* only -- keys stay in the artifact, as everywhere else."""
    by_status: Dict[str, int] = {}
    checks: Dict[str, int] = {}
    failed_checks: Dict[str, int] = {}
    queries = 0
    for app in artifact["applications"]:
        by_status[app["status"]] = by_status.get(app["status"], 0) + 1
        queries += len(app["layer4"])
        for check in app["checks"]:
            checks[check["status"]] = checks.get(check["status"], 0) + 1
            if check["status"] == "fail":
                failed_checks[check["check"]] = failed_checks.get(check["check"], 0) + 1
    summary: Dict[str, Any] = {
        "command": "verify",
        "applications": len(artifact["applications"]),
        "applicationsByStatus": by_status,
        "layer1ChecksByStatus": checks,
        "layer4QueriesEmitted": queries,
    }
    if failed_checks:
        summary["failedChecks"] = failed_checks
    return summary


def load_apply_artifact(path: Path) -> Dict[str, Any]:
    """The applying run's own record, which is the only place the merge decisions are written.

    The plan says what was intended. Whether a key was added, already there and kept, or replaced
    is a fact about the tenant at the moment of the write, and nothing but the applying run knows
    it -- so the notebook reads it here rather than inferring it.
    """
    if not path.exists():
        raise UsageError(
            f"no applying run at {path}. The results notebook reports what reached the tenant, "
            "which is recorded by `apply` -- point --apply at its apply.json.",
            fix=["Pass --apply PATH naming the apply.json of a run that wrote to the tenant."],
        )
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"{path} could not be read as JSON: {exc}", fix=["Pass --apply PATH naming the apply.json of a run that wrote to the tenant."]) from exc
    if not isinstance(artifact, dict) or artifact.get("artifact") != "apply":
        raise UsageError(
            f"{path} is not an applying run -- it carries {artifact.get('artifact')!r} rather "
            "than 'apply'.",
            fix=["Pass --apply PATH naming the apply.json of a run that wrote to the tenant."],
        )
    if artifact.get("dryRun"):
        raise UsageError(
            f"{path} is a dry run, so nothing in it reached the tenant. A results notebook built "
            "from it would report changes that were never made. Run `apply` without --dry-run "
            "first, then point --apply at the apply.json it writes.",
            fix=["Run `apply` without --dry-run, then `verify --notebook` again."],
        )
    return artifact


def command_verify(args: argparse.Namespace) -> int:
    """The configuration read-back, run; the agent and Grail checks, emitted. Reads only.

    The read-back is the gate; the Grail checks are delayed confirmation, so this phase answers
    what can be answered the moment the write lands and hands the rest over as something to run
    later. Executing the layer-4 queries here would turn "no traffic yet" into
    a failure verdict, which is the single most likely way to report a good migration as a bad
    one.
    """
    if not str(args.out_dir).strip():
        raise UsageError(
            "--out-dir is empty. Name the directory the artifacts are in.", fix=FIX_OUT_DIR
        )
    out_dir = Path(args.out_dir)
    plan_path = Path(args.plan) if args.plan else out_dir / "plan.json"
    plan = load_plan_artifact(plan_path, phase="verify")

    backup_path: Optional[Path] = None
    backup: Optional[Dict[str, Any]] = None
    if not args.no_backup:
        backup_path = Path(args.backup) if args.backup else latest_backup(out_dir)
        if backup_path:
            backup = load_backup_artifact(backup_path)

    settings = load_settings(config_path=Path(args.config) if args.config else None)
    client, token_source = settings_client(settings, timeout=args.timeout, phase="verify")
    progress = None if args.quiet else progress_to_stderr
    host = classic_host(settings)
    refuse_other_tenant((plan.get("source") or {}).get("environment"), plan_path, host=host)

    results, errors = verify_applications(
        client, plan, backup=backup, only_ids=args.application or None, progress=progress
    )
    artifact = verify_artifact(
        results,
        classic_host=host,
        plan_path=str(plan_path.resolve()),
        backup_path=str(backup_path.resolve()) if backup_path else None,
    )
    path = write_artifact(out_dir, "verify.json", artifact)
    queries_path = write_text_artifact(out_dir, "verify-queries.dql", queries_document(artifact))

    notebook_path: Optional[Path] = None
    notebook_warnings: List[str] = []
    if args.notebook is not None:
        apply_path = Path(args.apply) if args.apply else out_dir / "apply.json"
        notebook = notebook_artifact(plan, load_apply_artifact(apply_path))
        notebook_warnings = notebook_problems(notebook)
        name = args.notebook.strip() or NOTEBOOK_FILENAME
        notebook_path = write_artifact(out_dir, name, notebook)

    summary = summarise_verify(artifact)
    summary["tenant"] = host
    summary["tokenFrom"] = token_source
    summary["backup"] = str(backup_path.resolve()) if backup_path else None
    summary["artifact"] = str(path)
    summary["queries"] = str(queries_path)
    if notebook_path:
        summary["notebook"] = str(notebook_path)
        # A notebook that fails its own checks is still written -- the tables in it are the
        # record of what happened, and deleting them over a malformed query helps nobody. What
        # is not acceptable is handing it over without saying so.
        if notebook_warnings:
            summary["notebookProblems"] = notebook_warnings
    verified = summary["applicationsByStatus"].get("verified", 0)
    if not verified and (errors or summary["applicationsByStatus"].get("failed")):
        summary["status"] = "failed"
    elif errors or summary["applicationsByStatus"].get("failed") or summary[
        "applicationsByStatus"
    ].get("incomplete"):
        summary["status"] = "partial"
    else:
        summary["status"] = "ok"
    if summary["applicationsByStatus"].get("incomplete") and not summary.get("failedChecks"):
        summary["nextStep"] = (
            "Layer 1 passed what it could check. A skipped check is a check that had no input "
            "-- point --backup at the applying run's backup-<stamp>.json to prove the merge "
            "kept what was already there."
        )
    verify_guide(summary)
    print(json.dumps(summary, indent=2))

    if summary["status"] == "failed":
        return EXIT_API
    return EXIT_PARTIAL if summary["status"] == "partial" else EXIT_OK


# ------------------------------------------------------------------ the restore phase


class RestoreRecord:
    """One application's pass through `restore`: what the backup holds, what is there now.

    The passes are the three `apply` uses, for the reason `apply` uses them: everything is read
    before anything is written, so the snapshot this run takes of the current state covers the
    whole batch rather than whatever had not been reached yet.
    """

    def __init__(self, entry: Dict[str, Any]) -> None:
        self.id: str = str(entry.get("id") or "")
        self.kind: str = str(entry.get("kind") or "")
        self.schema_id: str = str(entry.get("schemaId") or "")
        self.scope: str = str(entry.get("scope") or "")
        self.existed: bool = bool(entry.get("existed"))
        value = entry.get("value")
        self.backup_value: Optional[Dict[str, Any]] = value if isinstance(value, dict) else None
        self.current: Optional[Dict[str, Any]] = None
        self.intent: Optional[str] = None
        self.delta: Dict[str, int] = {"restored": 0, "removed": 0}
        self.action: str = "pending"
        self.warnings: List[Dict[str, Any]] = []
        self.error: Optional[Dict[str, Any]] = None

    def result(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "schemaId": self.schema_id,
            "action": self.action,
            "intent": self.intent,
            "existedBefore": self.existed,
            "presentNow": self.current is not None,
            "objectId": (self.current or {}).get("objectId"),
            "entriesRestored": self.delta["restored"],
            "entriesRemoved": self.delta["removed"],
            "warnings": self.warnings,
            "error": self.error,
        }


def restore_records(backup: Dict[str, Any], *, source: str) -> List[RestoreRecord]:
    """The backup's applications, as records. A malformed entry stops the run before any read."""
    records = []
    for entry in backup.get("applications") or []:
        if not isinstance(entry, dict):
            raise UsageError(
                f"{source} lists an application that is not an object.", fix=FIX_FOREIGN_BACKUP
            )
        record = RestoreRecord(entry)
        if not record.id or not record.schema_id or not record.scope:
            raise UsageError(
                f"{source} lists an application without an id, a schemaId or a scope, so there "
                "is no way to find what it refers to. Restore from a backup this tool wrote.",
                fix=FIX_FOREIGN_BACKUP,
            )
        # `restore` is the one command that deletes a tenant object, so the backup may only
        # point it at the two schemas `apply` writes -- never at whatever a hand-edited or
        # foreign file names.
        if record.schema_id not in SCHEMA_BY_KIND.values():
            raise UsageError(
                f"{source} names schemaId {record.schema_id!r}, which this tool never writes. "
                "Restore from a backup this tool wrote.",
                fix=FIX_FOREIGN_BACKUP,
            )
        records.append(record)
    return records


def restore_delta(
    current_value: Optional[Dict[str, Any]], backup_value: Optional[Dict[str, Any]]
) -> Dict[str, int]:
    """How many entries writing the backup back would put there, and how many it would take away.

    `removed` is the number worth reading twice: it counts properties the tenant has now and the
    backup does not. Some of them are what the run you are undoing added, which is the point;
    any others were added afterwards, and going back to the backup takes them with it.
    """
    restored = removed = 0
    for field in (CAPTURED, DECLARED):
        current = _entries_by_key(current_value, field)
        backup = _entries_by_key(backup_value, field)
        removed += sum(1 for key in current if key not in backup)
        restored += sum(1 for key, entry in backup.items() if current.get(key) != entry)
    return {"restored": restored, "removed": removed}


def read_objects_to_restore(
    client: HttpClient,
    records: List[RestoreRecord],
    *,
    only_ids: Optional[Iterable[str]] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Pass one: what does the tenant hold now, for every application the backup covers?"""
    report = progress or (lambda _message: None)
    wanted = {value.strip() for value in only_ids} if only_ids else None
    if wanted:
        missing = sorted(wanted - {record.id for record in records})
        if missing:
            raise UsageError(
                "--application named "
                + ", ".join(missing)
                + ", which this backup does not cover. `restore` writes back only what was "
                "backed up.",
                fix=[
                    "Name only applications the backup lists under `applications`, or leave "
                    "--application out.",
                    "Or pass --backup PATH naming the backup of the run that wrote them.",
                ],
            )
        for record in records:
            if record.id not in wanted:
                record.action = "not-selected"

    errors: List[Dict[str, Any]] = []
    selected = [record for record in records if record.action == "pending"]
    for position, record in enumerate(selected, start=1):
        report(f"reading settings {position}/{len(selected)}: {record.id}")
        try:
            record.current = read_settings_object(
                client, schema_id=record.schema_id, scope=record.scope
            )
        except ApiError as exc:
            record.action = "failed"
            record.error = _api_error_entry(record.id, "read", exc)
            errors.append(record.error)
    return errors


def decide_restore(records: Iterable[RestoreRecord]) -> List[Dict[str, Any]]:
    """Pass two: what each application needs. Makes no request and writes nothing.

    An object the run created is deleted rather than emptied: an empty object is a configuration
    that says "capture nothing", and that is not what was there before.
    """
    problems: List[Dict[str, Any]] = []
    for record in records:
        if record.action != "pending":
            continue
        current_value = (record.current or {}).get("value")
        current_value = current_value if isinstance(current_value, dict) else None

        if record.existed and record.backup_value is None:
            # The backup says an object was there and carries nothing to put back. Emptying the
            # object or deleting it are both guesses, and one of them is unrecoverable.
            record.action = "refused"
            record.error = {
                "applicationId": record.id,
                "stage": "decide",
                "status": 0,
                "message": "the backup records that a settings object existed but holds no "
                "value for it, so there is nothing to write back.",
                "whatToDo": [
                    "Look in --out-dir for an earlier backup-<stamp>.json that holds a value for "
                    f"it, and run `restore --backup PATH --application {record.id}`."
                ],
            }
            problems.append(record.error)
            continue

        if record.existed:
            record.intent = "recreate" if record.current is None else "rewrite"
        elif record.current is None:
            # Already gone -- the run being undone created it and it is no longer there.
            record.action = "already-absent"
            continue
        else:
            record.intent = "delete"

        if record.intent == "delete":
            record.delta = restore_delta(current_value, None)
        else:
            record.delta = restore_delta(current_value, record.backup_value)
            if record.intent == "rewrite" and current_value == record.backup_value:
                record.action = "unchanged"
                record.intent = None
    return problems


def pre_restore_artifact(
    records: Iterable[RestoreRecord],
    *,
    classic_host: str,
    backup_path: Optional[str] = None,
    pipeline: Optional[PipelineRestore] = None,
) -> Dict[str, Any]:
    """What the tenant holds *now*, written before the first write of the restore.

    A restore is a write like any other, so it takes its own snapshot first, in the same shape
    as the one it is about to apply: point `restore --backup` at this file and you undo the
    undo. It is named `pre-restore-<stamp>.json` rather than `backup-<stamp>.json` so that
    nothing looking for "the newest backup" picks up the state of a migrated tenant.
    """
    return {
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "artifact": "backup",
        "takenBy": "restore",
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "capturedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": {"classicHost": classic_host},
        "source": {"backup": backup_path},
        "applications": [
            {
                "id": record.id,
                "kind": record.kind,
                "schemaId": record.schema_id,
                "scope": record.scope,
                "existed": record.current is not None,
                "objectId": (record.current or {}).get("objectId"),
                "schemaVersion": (record.current or {}).get("schemaVersion"),
                "updateToken": (record.current or {}).get("updateToken"),
                "value": (record.current or {}).get("value"),
            }
            for record in records
            if record.action == "pending"
        ],
        "pipeline": pipeline.snapshot() if pipeline is not None and pipeline.pending() else None,
    }


def write_restore(
    client: HttpClient,
    records: Iterable[RestoreRecord],
    *,
    dry_run: bool = False,
    progress: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Pass three: write the backup back. Every record is handled in isolation."""
    report = progress or (lambda _message: None)
    errors: List[Dict[str, Any]] = []
    pending = [r for r in records if r.action == "pending"]
    versions: Dict[str, str] = {}

    for position, record in enumerate(pending, start=1):
        if dry_run:
            record.action = "dry-run"
            continue
        try:
            if record.intent == "recreate":
                version = resolve_schema_version(client, record.schema_id, versions)
                report(f"creating settings {position}/{len(pending)}: {record.id}")
                client.send_json(
                    "POST",
                    SETTINGS_OBJECTS,
                    [
                        {
                            "schemaId": record.schema_id,
                            "schemaVersion": version,
                            "scope": record.scope,
                            "value": record.backup_value,
                        }
                    ],
                )
                record.action = "recreated"
                continue

            object_id = str((record.current or {}).get("objectId") or "")
            if not object_id:
                raise ApiError(
                    0, "the settings object on the tenant reports no objectId", SETTINGS_OBJECTS,
                    fix=FIX_UNEXPECTED,
                )
            quoted = urllib.parse.quote(object_id, safe="")

            if record.intent == "delete":
                report(f"deleting settings {position}/{len(pending)}: {record.id}")
                client.delete(f"{SETTINGS_OBJECTS}/{quoted}")
                record.action = "deleted"
                continue

            body: Dict[str, Any] = {"value": record.backup_value}
            current = record.current or {}
            if current.get("schemaVersion"):
                body["schemaVersion"] = current["schemaVersion"]
            token = current.get("updateToken")
            if token:
                # The optimistic-lock token comes from the read this run just did, never from
                # the backup: the run being undone is what invalidated the one in the backup, so
                # sending that would reject every restore of a run that worked.
                body["updateToken"] = token
            else:
                record.warnings.append(unlocked_write_warning())
            report(f"restoring settings {position}/{len(pending)}: {record.id}")
            client.send_json("PUT", f"{SETTINGS_OBJECTS}/{quoted}", body)
            record.action = "restored"
        except ApiError as exc:
            record.action = "failed"
            record.error = _api_error_entry(record.id, "write", exc)
            errors.append(record.error)
    return errors


# ---------------------------------------------------------- restoring the pipeline half

PROCESSOR_ID_PREFIX = "rum-"


class PipelineRestore:
    """The pipeline half of a backup, and what the tenant holds now.

    Routing is never written back wholesale. It is one object shared by everything that routes
    records in the environment, and another team may have changed it since: only the entries
    for this tool's pipeline are taken out (or put back as the backup had them), and every other
    entry stays as it is now. The same goes for an existing pipeline that was joined: exactly
    the processors this tool added are removed.
    """

    def __init__(self, saved: Dict[str, Any], *, source: str) -> None:
        self.host = str(saved.get("platformHost") or "")
        self.mode = str(saved.get("mode") or "")
        self.custom_id = str(saved.get("customId") or "")
        self.existed = bool(saved.get("existed"))
        self.value: Optional[Dict[str, Any]] = saved.get("value") if isinstance(saved.get("value"), dict) else None
        self.object_id_before = saved.get("objectId")
        self.processor_ids: List[str] = [str(i) for i in saved.get("processorIds") or []]
        routing = saved.get("routing") if isinstance(saved.get("routing"), dict) else {}
        self.routing_before: Dict[str, Any] = routing.get("value") if isinstance(routing.get("value"), dict) else {}
        # `restore` deletes and rewrites platform objects, so a backup may only point it at the
        # pipeline this tool creates, or at processors this tool named.
        if self.mode == "new" and self.custom_id != NEW_PIPELINE_ID:
            raise UsageError(
                f"{source} names pipeline {self.custom_id!r}, which this tool never creates. "
                "Restore from a backup this tool wrote.",
                fix=FIX_FOREIGN_BACKUP,
            )
        if self.mode not in ("new", "existing") or not self.custom_id:
            raise UsageError(
                f"{source} has a pipeline section this tool did not write.",
                fix=FIX_FOREIGN_BACKUP + [
                    "Or restore the capture settings alone with `restore --capture-only`."
                ],
            )
        if any(not i.startswith(PROCESSOR_ID_PREFIX) for i in self.processor_ids):
            raise UsageError(
                f"{source} lists a processor this tool never names. Restore from a backup this "
                "tool wrote.",
                fix=FIX_FOREIGN_BACKUP,
            )
        self.pipeline: Optional[Dict[str, Any]] = None
        self.routing: Optional[Dict[str, Any]] = None
        self.pipeline_action = "pending"
        self.routing_action = "not-written" if self.mode == "existing" else "pending"
        self.warnings: List[str] = []
        self.error: Optional[Dict[str, Any]] = None
        self.client: Optional[HttpClient] = None

    @property
    def object_id(self) -> str:
        return str((self.pipeline or {}).get("objectId") or "")

    def entries_before(self) -> List[Dict[str, Any]]:
        """The routes this pipeline had before the run -- none, unless an earlier run made them."""
        if not self.existed or not self.object_id_before:
            return []
        return [
            dict(entry, pipelineId=self.object_id)
            for entry in self.routing_before.get("routingEntries") or []
            if entry.get("pipelineId") == self.object_id_before
        ]

    def pending(self) -> bool:
        return "pending" in (self.pipeline_action, self.routing_action)

    def snapshot(self) -> Dict[str, Any]:
        """The current state, in the shape of a backup's pipeline section."""
        return {
            "platformHost": self.host,
            "mode": self.mode,
            "customId": self.custom_id,
            "existed": self.pipeline is not None,
            "objectId": self.object_id or None,
            "value": (self.pipeline or {}).get("value"),
            "processorIds": self.processor_ids,
            "routing": None if self.routing is None else {
                "objectId": self.routing.get("objectId"), "value": self.routing.get("value"),
            },
        }

    def result(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "pipelineId": self.custom_id,
            "platformHost": self.host,
            "objectId": self.object_id or None,
            "pipelineAction": self.pipeline_action,
            "routingAction": self.routing_action,
            "warnings": self.warnings,
            "error": self.error,
        }


def read_pipeline_to_restore(
    client: HttpClient,
    record: PipelineRestore,
    *,
    progress: Optional[Callable[[str], None]] = None,
) -> None:
    report = progress or (lambda _message: None)
    report(f"reading the pipelines on {record.host}")
    try:
        record.pipeline = find_pipeline(client, record.custom_id)
        if record.mode == "new":
            report("reading the routing object")
            record.routing = read_routing(client)
    except ApiError as exc:
        raise ApiError(
            exc.status,
            f"the pipeline half could not be read on {record.host}: {exc.message}. Nothing was "
            "written. Fix the platform token or host, or re-run with --capture-only to restore "
            "the capture settings alone.",
            exc.url_path,
            fix=exc.what_to_do + [
                "Or restore the capture settings alone with `restore --capture-only`."
            ],
        ) from exc
    decide_pipeline_restore(record)


def decide_pipeline_restore(record: PipelineRestore) -> None:
    current = (record.pipeline or {}).get("value")
    if record.mode == "existing":
        record.routing_action = "not-written"
        if current is None:
            record.pipeline_action = "absent"
            record.warnings.append(
                f"pipeline {record.custom_id!r} is gone; there is nothing to remove its "
                "processors from"
            )
        elif any(p.get("id") in set(record.processor_ids) for p in processors_in(current)):
            record.pipeline_action = "pending"
        else:
            record.pipeline_action = "unchanged"
        return

    if record.pipeline is None:
        record.routing_action = "unchanged"
        record.pipeline_action = "absent"
        if record.existed:
            record.warnings.append(
                f"pipeline {record.custom_id!r} existed before the run and is gone now; it is "
                "not recreated"
            )
        return
    routing = (record.routing or {}).get("value") or {}
    desired = routing_with(routing, record.object_id, record.entries_before())
    record.routing_action = "unchanged" if desired == routing else "pending"
    if not record.existed:
        record.pipeline_action = "pending"
    elif current == record.value:
        record.pipeline_action = "unchanged"
    else:
        record.pipeline_action = "pending"


def write_pipeline_restore(
    client: HttpClient,
    record: PipelineRestore,
    *,
    dry_run: bool = False,
    progress: Optional[Callable[[str], None]] = None,
) -> List[Dict[str, Any]]:
    """Route first, then the pipeline -- so no route is ever left pointing at a deleted one."""
    if not record.pending():
        return []
    if dry_run:
        for name in ("pipeline_action", "routing_action"):
            if getattr(record, name) == "pending":
                setattr(record, name, "dry-run")
        return []
    report = progress or (lambda _message: None)
    try:
        if record.mode == "existing":
            report(f"removing this tool's processors from pipeline {record.custom_id}")
            fresh = read_platform_object(client, record.object_id)
            ids = set(record.processor_ids)
            kept = [p for p in processors_in(fresh["value"]) if p.get("id") not in ids]
            _validated_put(
                client, record.object_id, with_processors(fresh["value"], kept),
                fresh.get("version"), dry_run=False,
            )
            record.pipeline_action = "processors-removed"
            return []

        if record.routing_action == "pending":
            report("taking this tool's entries out of the routing object")
            routing_id = str((record.routing or {}).get("objectId") or "")
            fresh = read_platform_object(client, routing_id)
            value = routing_with(fresh["value"], record.object_id, record.entries_before())
            _validated_put(client, routing_id, value, fresh.get("version"), dry_run=False)
            record.routing_action = "restored"

        if record.pipeline_action == "pending":
            fresh = read_platform_object(client, record.object_id)
            if (
                fresh.get("schemaId") not in (None, OPENPIPELINE_PIPELINES_SCHEMA)
                or fresh["value"].get("customId") != NEW_PIPELINE_ID
            ):
                raise ApiError(
                    0, "the object at that id is no longer this tool's pipeline. The route was "
                    "already taken out; the pipeline was left alone.",
                    _object_path(record.object_id),
                    fix=[
                        "Nothing is left to undo for the pipeline: the object at that id now "
                        "belongs to something else. Restore the capture settings with "
                        "`restore --capture-only` if they are not restored yet."
                    ],
                )
            if record.existed and record.value is not None:
                report(f"writing pipeline {record.custom_id} back")
                _validated_put(
                    client, record.object_id, record.value, fresh.get("version"), dry_run=False
                )
                record.pipeline_action = "restored"
            else:
                report(f"deleting pipeline {record.custom_id}")
                client.delete(_object_path(record.object_id), _locked(fresh.get("version")))
                record.pipeline_action = "deleted"
    except ApiError as exc:
        record.error = {"stage": "pipeline", **exc.as_dict()}
        for name in ("pipeline_action", "routing_action"):
            if getattr(record, name) == "pending":
                setattr(record, name, "failed")
        return [record.error]
    return []


def restore_artifact(
    records: Iterable[RestoreRecord],
    *,
    classic_host: str,
    dry_run: bool,
    backup: Dict[str, Any],
    backup_path: Optional[str] = None,
    pre_restore_path: Optional[str] = None,
    pipeline: Optional[PipelineRestore] = None,
) -> Dict[str, Any]:
    return {
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "artifact": "restore",
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "restoredAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dryRun": dry_run,
        "environment": {"classicHost": classic_host},
        "source": {"backup": backup_path, "capturedAt": backup.get("capturedAt")},
        "preRestoreBackup": pre_restore_path,
        "applications": [record.result() for record in records],
        "pipeline": pipeline.result() if pipeline is not None else None,
    }


def summarise_restore(artifact: Dict[str, Any]) -> Dict[str, Any]:
    """Counts and action names only -- no keys, no capture expressions, same rule as the rest."""
    by_action: Dict[str, int] = {}
    restored = removed = problems = warnings = 0
    for app in artifact["applications"]:
        by_action[app["action"]] = by_action.get(app["action"], 0) + 1
        restored += app["entriesRestored"]
        removed += app["entriesRemoved"]
        warnings += len(app["warnings"])
        if app["error"]:
            problems += 1

    summary: Dict[str, Any] = {
        "command": "restore",
        "dryRun": artifact["dryRun"],
        "applications": len(artifact["applications"]),
        "applicationsByAction": by_action,
        "entriesRestored": restored,
        "entriesRemoved": removed,
        "problems": problems,
        "warnings": warnings,
    }
    pipeline = artifact.get("pipeline")
    if pipeline:
        summary["pipeline"] = {
            key: pipeline[key]
            for key in ("mode", "pipelineId", "platformHost", "pipelineAction", "routingAction")
        }
        summary["warnings"] += len(pipeline["warnings"])
        summary["pipelineWarnings"] = pipeline["warnings"]
        if pipeline["error"]:
            summary["problems"] += 1
            summary["pipelineError"] = pipeline["error"]
    if removed:
        tense = "would be removed" if artifact["dryRun"] else "were removed"
        summary["nextStep"] = (
            f"{removed} propert{'y' if removed == 1 else 'ies'} on the tenant {tense}: they are "
            "not in the backup. The ones the run you are undoing added are meant to go; anything "
            "added after it is in the pre-restore snapshot rather than lost."
        )
    if pipeline and pipeline["error"]:
        step = pipeline_next_step(pipeline, command="restore")
        summary["nextStep"] = f"{step} {summary['nextStep']}" if "nextStep" in summary else step
    return summary


def pipeline_to_restore(
    settings: Dict[str, str],
    backup: Dict[str, Any],
    args: argparse.Namespace,
    *,
    host: str,
    source: str,
    progress: Optional[Callable[[str], None]],
) -> Optional[PipelineRestore]:
    """The backup's pipeline half, read and decided -- or None when there is none to undo."""
    saved = backup.get("pipeline")
    if args.capture_only or not isinstance(saved, dict):
        return None
    if args.application:
        raise UsageError(
            f"{source} has a pipeline section, and the pipeline and its route serve every "
            "application the run wrote. --application narrows the capture half only: add "
            "--capture-only, or leave --application out.",
            fix=[
                "Add --capture-only to restore only the named applications' capture settings.",
                "Or leave --application out to undo the whole run, the pipeline included.",
            ],
        )
    record = PipelineRestore(saved, source=source)
    client, platform_host = platform_client(settings, timeout=args.timeout)
    refuse_other_platform(platform_host, host=host)
    if record.host and record.host != platform_host:
        raise UsageError(
            f"{source} was written against {record.host} and this run talks to "
            f"{platform_host}. Check DT_PLATFORM_BASE.",
            fix=[
                f"Set DT_PLATFORM_BASE to https://{record.host}, the host the backup was made on.",
                "Or pass --backup PATH naming a backup made on this environment.",
            ],
        )
    record.host = platform_host
    record.client = client
    read_pipeline_to_restore(client, record, progress=progress)
    return record


def command_restore(args: argparse.Namespace) -> int:
    """Undo an `apply` run by writing its backup back.

    It reads the whole batch first, snapshots what it is about to overwrite, and only then
    writes -- the same order `apply` uses, so that an interrupted restore is as recoverable as
    an interrupted apply.
    """
    if not str(args.out_dir).strip():
        raise UsageError(
            "--out-dir is empty. Name the directory the artifacts are in.", fix=FIX_OUT_DIR
        )
    out_dir = Path(args.out_dir)
    backup_path = Path(args.backup) if args.backup else latest_backup(out_dir)
    if backup_path is None:
        raise UsageError(
            f"no backup artifact in {out_dir}. `restore` undoes a run by writing that run's "
            "backup-<stamp>.json back, so it needs one, named with --backup or sitting in "
            "--out-dir. A dry run writes no backup, and neither does a run that changed nothing.",
            fix=[
                "Pass --backup PATH naming the backup-<stamp>.json of the run to undo.",
                "Or pass --out-dir DIR naming the directory that run wrote to.",
                "If the run was a dry run or changed nothing, there is nothing to undo.",
            ],
        )
    backup = load_backup_artifact(backup_path)

    settings = load_settings(config_path=Path(args.config) if args.config else None)
    client, token_source = settings_client(settings, timeout=args.timeout, phase="restore")
    progress = None if args.quiet else progress_to_stderr
    host = classic_host(settings)
    # Cheap, and the one mistake here that cannot be undone by running the phase again:
    # writing one tenant's configuration into another one.
    refuse_other_tenant(backup.get("environment"), backup_path, host=host)

    if args.capture_only and args.pipeline_only:
        raise UsageError(
            "--capture-only and --pipeline-only together write nothing. Pick one.",
            fix=["Keep one of the two flags, or drop both to run both halves."],
        )
    pipeline = pipeline_to_restore(settings, backup, args, host=host, source=str(backup_path),
                                   progress=progress)

    records: List[RestoreRecord] = []
    errors: List[Dict[str, Any]] = []
    if not args.pipeline_only:
        records = restore_records(backup, source=str(backup_path))
        errors = read_objects_to_restore(
            client, records, only_ids=args.application or None, progress=progress
        )
        errors.extend(decide_restore(records))

    pre_restore_path: Optional[Path] = None
    pipeline_pending = pipeline is not None and pipeline.pending()
    if not args.dry_run and (
        pipeline_pending or any(record.action == "pending" for record in records)
    ):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        pre_restore_path = write_artifact(
            out_dir,
            f"pre-restore-{stamp}.json",
            pre_restore_artifact(
                records, classic_host=host, backup_path=str(backup_path.resolve()),
                pipeline=pipeline,
            ),
        )

    # The reverse of `apply`'s order: the pipeline half first, and within it the route first.
    if pipeline is not None:
        errors.extend(
            write_pipeline_restore(
                pipeline.client, pipeline, dry_run=args.dry_run, progress=progress
            )
        )
    errors.extend(write_restore(client, records, dry_run=args.dry_run, progress=progress))

    artifact = restore_artifact(
        records,
        classic_host=host,
        dry_run=args.dry_run,
        backup=backup,
        backup_path=str(backup_path.resolve()),
        pre_restore_path=str(pre_restore_path) if pre_restore_path else None,
        pipeline=pipeline,
    )
    name = "restore-dry-run.json" if args.dry_run else "restore.json"
    path = write_artifact(out_dir, name, artifact)

    summary = summarise_restore(artifact)
    summary["tenant"] = host
    summary["tokenFrom"] = token_source
    summary["backup"] = str(backup_path.resolve())
    summary["preRestoreBackup"] = str(pre_restore_path) if pre_restore_path else None
    summary["artifact"] = str(path)
    written = sum(
        summary["applicationsByAction"].get(action, 0)
        for action in ("restored", "recreated", "deleted", "dry-run")
    )
    if pipeline is not None:
        written += sum(
            1
            for action in (pipeline.pipeline_action, pipeline.routing_action)
            if action in ("restored", "deleted", "processors-removed", "dry-run")
        )
    summary["status"] = (
        "failed" if errors and not written
        else "partial" if errors
        else "ok"
    )
    if not summary["applications"] and pipeline is None:
        summary["nextStep"] = (
            f"{backup_path} lists no application, so there is nothing to write back. A backup "
            "holds only what its run was about to change."
        )
    restore_guide(summary, args)
    print(json.dumps(summary, indent=2))

    if summary["status"] == "failed":
        return EXIT_API
    return EXIT_PARTIAL if summary["status"] == "partial" else EXIT_OK


# --------------------------------------------------------------- the results notebook

NOTEBOOK_SCHEMA_VERSION = "7"
NOTEBOOK_TIMEFRAME = {"from": "now()-2h", "to": "now()"}
NOTEBOOK_APPS_PER_TILE = 5

# The title the notebook carries inside it. Which of these two names you see depends on how the
# file reaches your environment: upload it by hand and the notebook is titled after the file, apply
# it through an API or a command line and this is the title. Both are written to say the same
# thing, so the notebook is recognisable in a list either way.
NOTEBOOK_NAME = "RUM property migration results"
NOTEBOOK_FILENAME = "rum-property-migration-results.json"

# The six buckets, in the order they are written: the key, the heading, and the line that stands
# in for an empty table. An empty bucket still gets its section -- a missing heading reads as
# something forgotten, where "nothing here" is an answer.
NOTEBOOK_BUCKETS = (
    (
        "clean",
        "Migrated - no additional work needed",
        "_Nothing migrated cleanly without follow-up._",
    ),
    ("overwritten", "Overwritten", "_Nothing was overwritten._"),
    (
        "needsOpenPipeline",
        "Migrated - requires OpenPipeline configuration",
        "_Nothing needs OpenPipeline follow-up._",
    ),
    (
        "unsupportedDnt",
        "Migrated - Do Not Track setting dropped",
        "_Nothing had a Do Not Track setting._",
    ),
    ("cannotMigrate", "Could not be migrated", "_Nothing was blocked from migrating._"),
    ("skipped", "Skipped", "_Nothing was skipped._"),
)

# Only properties that actually reached the tenant are queried. A null-rate check on a property
# that was never written returns nothing and invites you to read it as a broken migration.
NOTEBOOK_WRITTEN_BUCKETS = ("clean", "overwritten", "needsOpenPipeline", "unsupportedDnt")

EVENT_PROPERTY_PREFIX = "event_properties."
SESSION_PROPERTY_PREFIX = "session_properties."


def _escape_cell(value: Any) -> str:
    """A pipe in a display name or a note splits the markdown row it lands in."""
    return str("" if value is None else value).replace("|", "\\|").replace("\n", " ")


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def notebook_field_references(row: Dict[str, Any]) -> List[str]:
    """Where this property's values will be, once they arrive.

    The prefix follows the property, not a constant. A property reported into the session
    namespace lands under `session_properties.`, and an `event_properties.` reference to it
    counts zero on every record -- which reads exactly like a migration that did not work.

    A promoted property gets **both**. The pipeline rule copies the value into the session and
    leaves the event property where it was, so the two counts together tell "the capture works
    but the promotion does not" from "nothing is arriving at all".

    Unless the promotion was asked to take the carrier with it. Then there is one reference
    again, and it is the session one -- an `event_properties.` tile for a field the pipeline
    removes counts zero on every record, which is the exact failure this function exists to
    avoid, arrived at from the other direction.
    """
    key = row.get("key")
    if not key:
        return []
    promoted = any(
        rule.get("rule") == "session-property-promotion" for rule in row.get("pipeline") or []
    )
    if promoted and row.get("dropsEventProperty"):
        return [SESSION_PROPERTY_PREFIX + key]
    if promoted:
        return [EVENT_PROPERTY_PREFIX + key, SESSION_PROPERTY_PREFIX + key]
    if row.get("sessionScoped") and row.get("settingsField") == DECLARED:
        return [SESSION_PROPERTY_PREFIX + key]
    return [EVENT_PROPERTY_PREFIX + key]


def _blocked_reason(row: Dict[str, Any]) -> str:
    if row.get("blockedReason"):
        return str(row["blockedReason"])
    for flag in row.get("flags") or []:
        if flag.get("blocking"):
            return str(flag.get("detail") or flag.get("flag"))
    return "this property has no Grail equivalent."


def _lossy_notes(row: Dict[str, Any]) -> List[str]:
    return [
        str(flag.get("detail") or flag.get("flag"))
        for flag in row.get("flags") or []
        if not flag.get("blocking")
    ]


def _apply_index(applied: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The applying run, keyed the way the plan is read: application, then property key."""
    index: Dict[str, Dict[str, Any]] = {}
    for record in applied.get("applications") or []:
        entries = {}
        for decision in record.get("entries") or []:
            key = decision.get("propertyKey")
            if key:
                entries[key] = decision
        index[str(record.get("id"))] = {"record": record, "entries": entries}
    return index


def _notebook_item(
    app: Dict[str, Any], row: Dict[str, Any], reason: str, *, order: int = 0
) -> Dict[str, Any]:
    return {
        # Where this property sat in the plan. A property can land in two buckets, and the order
        # it is read back in should be the order it was planned in rather than whichever bucket
        # happened to claim it first.
        "order": order,
        "appName": app.get("name") or app.get("id"),
        "applicationId": app.get("id"),
        "kind": app.get("kind"),
        "displayName": row.get("displayName") or row.get("classicKey"),
        "key": row.get("classicKey"),
        "entryKey": row.get("key"),
        "reason": reason,
        "fieldReferences": notebook_field_references(row),
    }


def notebook_buckets(plan: Dict[str, Any], applied: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Every planned property, sorted into the six buckets the notebook reports.

    The buckets are not exclusive, and that is deliberate: a property can be both overwritten and
    in need of a pipeline rule, and hiding one of those behind the other loses a fact. `clean` is
    the exception -- it means *nothing else applies*, so it is only ever reached on its own.

    What went to the tenant is read from the applying run rather than re-derived from the plan.
    A plan says what was intended; only the run that wrote knows what the tenant already had.
    """
    buckets: Dict[str, List[Dict[str, Any]]] = {name: [] for name, _, _ in NOTEBOOK_BUCKETS}
    index = _apply_index(applied)
    order = 0
    for app in plan.get("applications") or []:
        applied_app = index.get(str(app.get("id")))
        for row in app.get("properties") or []:
            order += 1

            def _item(reason: str) -> Dict[str, Any]:
                return _notebook_item(app, row, reason, order=order)

            record = (applied_app or {}).get("record") or {}
            decision = ((applied_app or {}).get("entries") or {}).get(row.get("key"))

            if row.get("blocked"):
                buckets["cannotMigrate"].append(_item(_blocked_reason(row)))
                continue
            if record.get("action") == "failed":
                message = ((record.get("error") or {}).get("message")) or "the write did not succeed"
                buckets["cannotMigrate"].append(
                    _item(f"the write failed: {message}")
                )
                continue
            if row.get("decisionPending"):
                buckets["skipped"].append(
                    _item("this one is waiting on your choice of how to keep it on the session, "
                        "so nothing was written for it. Choose, and the plan is made again.",
                    )
                )
                continue
            if not row.get("settingsField"):
                buckets["skipped"].append(
                    _item("this property claims no Grail setting, so nothing was written."
                    )
                )
                continue
            if applied_app is None or decision is None:
                buckets["skipped"].append(
                    _item("the applying run did not cover this property, so whether it reached the "
                        "tenant is not recorded.",
                    )
                )
                continue
            action = decision.get("action")
            if action == "kept-existing":
                buckets["skipped"].append(
                    _item(str(
                            decision.get("detail")
                            or "this key was already there with a different definition, and it "
                            "was kept."
                        ),
                    )
                )
                continue

            placed = False
            if action == "replaced":
                buckets["overwritten"].append(
                    _item("a Grail property with this key was already there and was replaced, "
                        "because the run was asked to overwrite.",
                    )
                )
                placed = True
            dnt = [
                flag for flag in row.get("flags") or [] if flag.get("flag") == "privacy-regression"
            ]
            if dnt:
                buckets["unsupportedDnt"].append(
                    _item(str(dnt[0].get("detail")))
                )
                placed = True
            if row.get("pipeline"):
                rules = ", ".join(
                    sorted({str(rule.get("rule")) for rule in row["pipeline"] if rule.get("rule")})
                )
                buckets["needsOpenPipeline"].append(
                    _item(f"needs an OpenPipeline rule before it is complete: {rules}."
                    )
                )
                placed = True
            if not placed:
                buckets["clean"].append(_item("; ".join(_lossy_notes(row))))
    return buckets


def notebook_written_items(buckets: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """The written properties, once each, in the order they were planned.

    A property in two buckets is one property. Counting the buckets instead over-reports the
    headline number, and querying them twice puts the same block in a tile twice.
    """
    seen = set()
    items = []
    for name in NOTEBOOK_WRITTEN_BUCKETS:
        for item in buckets.get(name) or []:
            fingerprint = (item["applicationId"], item["key"])
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            items.append(item)
    # Back into the order they were planned in. Bucket order is an artifact of how they were
    # sorted, and the tables above read top to bottom in plan order -- so should the query.
    return sorted(items, key=lambda item: item["order"])


def notebook_pairs(items: Iterable[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """One block per (application, field reference), in planning order, deduplicated."""
    pairs: List[Tuple[str, str, str]] = []
    seen = set()
    for item in items:
        for reference in item["fieldReferences"]:
            fingerprint = (item["applicationId"], reference)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            pairs.append((item["applicationId"], item["appName"], reference))
    return pairs


def _notebook_block(application_id: str, reference: str, indent: str = "") -> str:
    """One application, one property, counted two ways.

    Every block pins one application and one property. Nothing is combined: two applications that
    share a property key would otherwise have their counts added together, and the sum answers a
    question nobody asked.
    """
    session = reference.startswith(SESSION_PROPERTY_PREFIX)
    lines = [f"fetch {'user.sessions' if session else 'user.events'}"]
    # Synthetic monitoring writes to both of these tables and carries none of these properties,
    # so an unfiltered count reads as a failed migration.
    lines.append(f"| {RUM_SOURCE_FILTER}")
    if session:
        lines.extend(session_scope_lines(application_id))
    else:
        lines.append(
            f'| filter dt.rum.instrumentation.id == "{instrumentation_id(application_id)}"'
        )
        # Events that could never carry an action property would otherwise inflate the empty
        # count and make a healthy migration look thin. Sessions have no such characteristic.
        lines.append("| filter characteristics.has_user_action == true")
    lines.extend(
        [
            "| summarize {",
            f"    null_count = countIf(isNull(`{reference}`)),",
            f"    non_null_count = countIf(isNotNull(`{reference}`))",
            "  },",
            "  by: {",
            f'    application = "{application_id}",',
            f'    property = "{reference}"',
            "  }",
        ]
    )
    return "\n".join(indent + line for line in lines)


def notebook_query(pairs: List[Tuple[str, str, str]]) -> str:
    """The tile's query: the first block is the pipeline, every other one is appended to it."""
    if not pairs:
        return ""
    application_id, _name, reference = pairs[0]
    parts = [_notebook_block(application_id, reference)]
    for application_id, _name, reference in pairs[1:]:
        parts.append("| append [")
        parts.append(_notebook_block(application_id, reference, "    "))
        parts.append("  ]")
    parts.append("| sort application asc, property asc")
    return "\n".join(parts)


def _markdown_section(markdown: str) -> Dict[str, Any]:
    return {"id": str(uuid.uuid4()), "type": "markdown", "markdown": markdown}


def _dql_section(query: str) -> Dict[str, Any]:
    """A query section, with no cached result in it.

    A notebook exported from the product carries the results of its last run. This one carries
    none: the query runs when you open it. Numbers written in here by the tool that made the
    change would look like a measurement of that change, and they would not be one.
    """
    return {
        "id": str(uuid.uuid4()),
        "type": "dql",
        "showTitle": False,
        "drilldownPath": [],
        "filterSegments": [],
        "previousFilterSegments": [],
        "showInput": True,
        "state": {
            "input": {"timeframe": dict(NOTEBOOK_TIMEFRAME), "value": query},
            "visualizationSettings": {
                "table": {"hideColumnsForLargeResults": True},
                "chartSettings": {},
            },
            "querySettings": {
                "maxResultRecords": 1000,
                "defaultScanLimitGbytes": 500,
                "maxResultMegaBytes": 1,
                "defaultSamplingRatio": 10,
                "enableSampling": False,
            },
            "visualization": "table",
            "davis": {"includeLogs": True, "davisVisualization": {"isAvailable": True}},
        },
    }


def _bucket_table(items: List[Dict[str, Any]], heading: str, empty: str) -> str:
    lines = [f"## {heading}", ""]
    if not items:
        lines.append(empty)
        return "\n".join(lines)
    lines.append("| App Name | Property Name | Key | Notes |")
    lines.append("| --- | --- | --- | --- |")
    for item in items:
        lines.append(
            "| {app} | {name} | `{key}` | {notes} |".format(
                app=_escape_cell(item["appName"]),
                name=_escape_cell(item["displayName"]),
                key=_escape_cell(item["key"]),
                notes=_escape_cell(item["reason"]),
            )
        )
    return "\n".join(lines)


def _summary_markdown(buckets: Dict[str, List[Dict[str, Any]]], written: List[Dict[str, Any]]) -> str:
    applications = []
    for item in written:
        if item["appName"] not in applications:
            applications.append(item["appName"])
    counts = {name: len(buckets.get(name) or []) for name, _, _ in NOTEBOOK_BUCKETS}
    lines = [
        "**{n} {properties}** migrated across **{m} {apps}**{names}.".format(
            n=len(written),
            properties=_plural(len(written), "property", "properties"),
            m=len(applications),
            apps=_plural(len(applications), "app", "apps"),
            names=(": " + ", ".join(_escape_cell(name) for name in applications))
            if applications
            else "",
        ),
        "",
        f"- Migrated without any additional work: {counts['clean']}",
        f"- Overwritten (existing Grail property replaced): {counts['overwritten']}",
        f"- Migrated but needs OpenPipeline configuration: {counts['needsOpenPipeline']}",
        f"- Migrated but has an unsupported setting (Do Not Track): {counts['unsupportedDnt']}",
        f"- Could not be migrated: {counts['cannotMigrate']}",
        f"- Skipped: {counts['skipped']}",
        "",
        "A property is attached to some of an application's events, not all of them. A non-zero "
        "`non_null_count` is the pass condition, and `null_count` will normally be the larger "
        "number of the two. A property configured minutes ago needs traffic before it can appear "
        "at all, so give it time before reading a zero as a failure.",
        "",
        "Session properties are counted over sessions rather than events, and a session that "
        "visited more than one of your applications is counted once for each of them.",
    ]
    return "\n".join(lines)


def _user_tag_markdown(plan: Dict[str, Any]) -> Optional[str]:
    """User tagging, as its own section, or `None` when no application configured any.

    Its own section rather than rows in the property buckets, and not only because the columns
    differ. A property that does not migrate is a property nobody can chart; a user tag that
    does not migrate means visitors on that application stop being identified at all -- a
    different question, for a different reader, with a different answer. Burying the second in
    a table of the first is how it gets missed.
    """
    rows: List[str] = []
    lost: List[str] = []
    for app in plan.get("applications") or []:
        planned = app.get("userTags") or {}
        tags = planned.get("tags") or []
        if not tags:
            continue
        name = app.get("name") or app.get("id")
        for tag in tags:
            if tag["blocked"]:
                outcome = "**Not migrated**"
                note = next(
                    (
                        str(flag.get("detail"))
                        for flag in tag.get("flags") or []
                        if flag.get("blocking")
                    ),
                    str(tag.get("blockedReason") or "no Gen3 equivalent"),
                )
            else:
                outcome = "Migrated"
                note = f"reads `{EVENT_PREFIX}{tag['key']}`, sets `{USER_TAG_FIELD}`"
                if tag.get("reusesCaptureOf"):
                    note += "; shares the capture already migrated for that property"
                if tag.get("ignoreCase"):
                    note += "; lower-cased, as it was"
                if tag.get("pendingExpression"):
                    note += (
                        "; **the cleanup rule `{rule}` still needs an expression from you** "
                        "(`plan --expression {key}=<expression>`) -- until it has one, none of "
                        "this application's tagging can be applied"
                    ).format(rule=tag.get("cleanupRule"), key=tag.get("expressionKey"))
            rows.append(
                "| {app} | {position} | {outcome} | {note} |".format(
                    app=_escape_cell(name),
                    position=tag["index"] + 1,
                    outcome=outcome,
                    note=_escape_cell(note),
                )
            )
        if not planned.get("migrating"):
            lost.append(f"{name} (`{app.get('id')}`)")

    if not rows:
        return None

    lines = [
        "## User tagging",
        "",
        "Classic user tagging has no Gen3 setting of its own, so each tag migrates as two "
        "pieces that only work together: a captured property, and one OpenPipeline statement "
        f"that copies it onto `{USER_TAG_FIELD}`. Applying the capture settings without the "
        "pipeline leaves the values captured and nobody identified.",
        "",
        "Order is significant and is preserved: within a user action the first tag that "
        "matches wins, which is why an application's tags become a single statement rather "
        "than one rule each.",
        "",
        "| App Name | Order | Outcome | Notes |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(rows)
    lines.extend(
        [
            "",
            f"Classic cropped a tag at {CLASSIC_USER_TAG_CROP} characters without saying so, "
            "and Gen3 does not crop at all. The longer value is kept rather than trimmed back, "
            "so a tag that was being shortened now arrives whole -- check anything downstream "
            "that was matching the shortened form.",
        ]
    )
    if lost:
        lines.extend(
            [
                "",
                "⚠ **No user tagging migrates for "
                + ", ".join(lost)
                + ".** Nothing will set a user identifier for "
                + ("it" if len(lost) == 1 else "them")
                + " after this migration unless `identifyUser()` is called from your own code.",
            ]
        )
    return "\n".join(lines)


def notebook_sections(
    buckets: Dict[str, List[Dict[str, Any]]],
    *,
    generated_on: str,
    plan: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    written = notebook_written_items(buckets)
    sections = [
        _markdown_section(f"# RUM Property Migration Results - {generated_on}"),
        _markdown_section(_summary_markdown(buckets, written)),
    ]
    for name, heading, empty in NOTEBOOK_BUCKETS:
        sections.append(_markdown_section(_bucket_table(buckets.get(name) or [], heading, empty)))

    user_tags = _user_tag_markdown(plan or {})
    if user_tags:
        sections.append(_markdown_section(user_tags))

    pairs = notebook_pairs(written)
    by_application: Dict[str, List[Tuple[str, str, str]]] = {}
    order: List[str] = []
    for pair in pairs:
        if pair[0] not in by_application:
            by_application[pair[0]] = []
            order.append(pair[0])
        by_application[pair[0]].append(pair)

    chunks = [
        order[position : position + NOTEBOOK_APPS_PER_TILE]
        for position in range(0, len(order), NOTEBOOK_APPS_PER_TILE)
    ]
    for position, chunk in enumerate(chunks, start=1):
        chunk_pairs = [pair for application_id in chunk for pair in by_application[application_id]]
        if not chunk_pairs:
            continue
        part = f" - Part {position} of {len(chunks)}" if len(chunks) > 1 else ""
        labels = ", ".join(
            "{name} (`{id}`)".format(
                name=_escape_cell(by_application[application_id][0][1]), id=application_id
            )
            for application_id in chunk
        )
        sections.append(
            _markdown_section(
                f"## Migrated Property Capture Status{part}\n\nApps in this table: {labels}"
            )
        )
        sections.append(_dql_section(notebook_query(chunk_pairs)))
    return sections


def notebook_artifact(
    plan: Dict[str, Any], applied: Dict[str, Any], *, generated_on: Optional[str] = None
) -> Dict[str, Any]:
    """The importable notebook: what happened, in prose, and what to check, as queries."""
    buckets = notebook_buckets(plan, applied)
    stamp = generated_on or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "name": NOTEBOOK_NAME,
        "version": NOTEBOOK_SCHEMA_VERSION,
        "defaultTimeframe": dict(NOTEBOOK_TIMEFRAME),
        "defaultSegments": [],
        "sections": notebook_sections(buckets, generated_on=stamp, plan=plan),
    }


def notebook_problems(notebook: Dict[str, Any]) -> List[str]:
    """The import contract, checked against what was just built rather than assumed.

    A notebook that fails any of these is rejected on import, or -- worse -- imported and read
    as a result. It costs a millisecond to check and it runs on every generated file.
    """
    problems: List[str] = []
    # Without a name, a notebook applied through an API or a command line is titled "Untitled
    # notebook" -- which is what you would have to open every one of them to tell apart.
    if not (notebook.get("name") or "").strip():
        problems.append("the notebook has no name, so it is titled for you rather than by you.")
    if notebook.get("version") != NOTEBOOK_SCHEMA_VERSION:
        problems.append(
            f"version is {notebook.get('version')!r} rather than the string "
            f"{NOTEBOOK_SCHEMA_VERSION!r}, which the import rejects."
        )
    sections = notebook.get("sections")
    if not isinstance(sections, list) or not sections:
        problems.append("the notebook has no sections.")
        return problems
    identifiers = [section.get("id") for section in sections]
    if len(set(identifiers)) != len(identifiers):
        problems.append("two sections share an id, so they collide when the notebook renders.")
    for position, section in enumerate(sections):
        heading = sections[position - 1] if position else {}
        if section.get("type") not in ("markdown", "dql"):
            problems.append(f"section {position} has type {section.get('type')!r}.")
        if section.get("type") != "dql":
            continue
        state = section.get("state") or {}
        if "result" in state:
            problems.append(
                f"section {position} carries a cached result, which presents numbers this tool "
                "never measured as if it had."
            )
        query = (state.get("input") or {}).get("value") or ""
        if not query.startswith("fetch user."):
            problems.append(f"section {position} does not start by fetching a table.")
        if not query.endswith("| sort application asc, property asc"):
            problems.append(f"section {position} does not end with the sort.")
        blocks = query.count("| summarize {")
        if query.count("| append [") != max(blocks - 1, 0):
            problems.append(
                f"section {position} has {blocks} blocks but "
                f"{query.count('| append [')} of them appended."
            )
        applications = set(re.findall(r'application = "([^"]+)"', query))
        if len(applications) > NOTEBOOK_APPS_PER_TILE:
            problems.append(
                f"section {position} covers {len(applications)} applications, and a tile holds "
                f"at most {NOTEBOOK_APPS_PER_TILE}."
            )
        # Whoever opens the tile reads the heading, not the query. An application counted in the
        # table and missing from the line above it is an unlabelled row.
        label = heading.get("markdown") or ""
        for application_id in sorted(applications):
            if application_id not in label:
                problems.append(
                    f"section {position} counts {application_id}, which the heading above it "
                    "does not name."
                )
        for reference in set(re.findall(r'property = "([^"]+)"', query)):
            if f"`{reference}`" not in query:
                problems.append(
                    f"section {position} labels {reference} without counting it under the same "
                    "name."
                )
        # Both of these return zero rather than an error, so nothing downstream would notice.
        if "dt.smartscape.frontend" in query:
            if 'smartscapeNodes "FRONTEND" | filter id_classic ==' not in query:
                problems.append(
                    f"section {position} resolves frontend ids without narrowing the lookup to "
                    "one application, so the lookup can be cut short before it reaches yours."
                )
            if re.search(r'"[^"]*"\s*,\s*dt\.smartscape\.frontend', query) or re.search(
                r"dt\.smartscape\.frontend\s*==", query
            ):
                problems.append(
                    f"section {position} compares dt.smartscape.frontend against a quoted id. "
                    "Its elements are Smartscape ids, so that match never succeeds."
                )
    return problems


# ------------------------------------------------------------------ the preflight phase
# Step 1 of the reference, as a command. It exists because a step with no command is a step an
# agent skips: the version, the enablement and the tenant itself all went unchecked in the
# first run that executed a migration end to end.

PREFLIGHT_FILENAME = "preflight.json"
ENABLEMENT_SCHEMA = "builtin:rum.web.enablement"
DEPRECATED_CAPTURE_SCHEMA = "builtin:rum.web.capture-custom-properties"
EFFECTIVE_VALUES = "/api/v2/settings/effectiveValues"
JAVASCRIPT_TAG = "/api/v2/rum/oneAgentJavaScriptTag"
# Below this, properties configured in the UI transfer and capture nothing.
MIN_RUM_JAVASCRIPT = (1, 341)
# The agent file names its version: `ruxitagent_<features>_10351261009050103.js` is 1.351 --
# the leading `1` the major, the next four digits the minor, then a build stamp.
AGENT_FILE_VERSION = re.compile(r"ruxitagent[^\"'/\s]*?_(\d)(\d{4})\d{6,}\.js")
PREFLIGHT_MAX_AGE_HOURS = 24

CONFIRM_HOST = (
    "This tool talks to {host}, read from DT_CLASSIC_BASE ({source}). It does not use dtctl, so "
    "a dtctl context or `dtctl doctor` says nothing about this tenant. Confirm this host with the "
    "user before going further."
)


def _gate(name: str, status: str, detail: str, **extra: Any) -> Dict[str, Any]:
    """One preflight result. `status` is ok, warn, block or unknown -- only `block` stops apply."""
    return {"gate": name, "status": status, "detail": detail, **extra}


def rum_javascript_version(tag: str) -> Optional[str]:
    """`1.351` from the agent file the tag loads, or None when the tag names none."""
    match = AGENT_FILE_VERSION.search(tag or "")
    if not match:
        return None
    return f"{match.group(1)}.{int(match.group(2))}"


def _version_tuple(version: str) -> Tuple[int, int]:
    major, _, minor = version.partition(".")
    return int(major), int(minor or 0)


def schema_gate(client: HttpClient) -> Dict[str, Any]:
    """The capture schema resolves, or the migration has nowhere to go."""
    try:
        payload = client.get_json(SETTINGS_SCHEMAS, {"pageSize": "500"})
    except ApiError as exc:
        return _gate("capture-schema", "block", f"the schema list could not be read: {exc.message}",
                     error=exc.as_dict(), whatToDo=exc.what_to_do)
    versions = {
        str(item.get("schemaId")): str(item.get("latestSchemaVersion") or "")
        for item in (payload.get("items") if isinstance(payload, dict) else None) or []
        if isinstance(item, dict)
    }
    wanted = SCHEMA_BY_KIND["web"]
    if wanted in versions:
        return _gate("capture-schema", "ok", f"{wanted} resolves", schemaVersion=versions[wanted])
    if DEPRECATED_CAPTURE_SCHEMA in versions:
        return _gate(
            "capture-schema", "block",
            f"only the deprecated {DEPRECATED_CAPTURE_SCHEMA} resolves. Stop and report it -- do "
            "not migrate onto the deprecated schema.",
            whatToDo=["Stop and tell the user: this tenant cannot take the migration yet."],
        )
    return _gate(
        "capture-schema", "block",
        f"{wanted} does not resolve. It is SaaS-only; on Dynatrace Managed nothing can be written.",
        whatToDo=["Stop and tell the user: this tenant cannot take the migration."],
    )


def write_gate(client: HttpClient, scope: str) -> Dict[str, Any]:
    """`settings.write`, checked by a validate-only create that the tenant evaluates and discards."""
    try:
        client.send_json(
            "POST",
            SETTINGS_OBJECTS,
            [{"schemaId": SCHEMA_BY_KIND["web"], "scope": scope, "value": {}}],
            {"validateOnly": "true"},
        )
    except ApiError as exc:
        if exc.status in (401, 403):
            return _gate(
                "settings-write", "block",
                "DT_CLASSIC_TOKEN cannot write settings: `apply` and `restore` need "
                "settings.write. scan, plan and verify still work.",
                error=exc.as_dict(),
                whatToDo=set_fix(
                    "DT_CLASSIC_TOKEN", "a classic API token with settings.read + settings.write"
                ) + ["Or stop after `plan`: scan, plan and verify need no write scope."],
            )
        return _gate("settings-write", "unknown", f"the validate-only write failed: {exc.message}",
                     error=exc.as_dict(), whatToDo=exc.what_to_do)
    return _gate("settings-write", "ok", "a validate-only write was accepted; nothing was stored")


def platform_gate(
    settings: Dict[str, str],
    *,
    timeout: float,
    make_client: Callable[..., HttpClient] = HttpClient,
) -> Dict[str, Any]:
    """The platform host and token, checked with one read of the routing object."""
    base, token = settings.get("DT_PLATFORM_BASE"), settings.get("DT_PLATFORM_TOKEN")
    if not base or not token:
        return _gate(
            "platform", "warn",
            "DT_PLATFORM_BASE or DT_PLATFORM_TOKEN is not set. The capture settings migrate "
            "without them; the pipeline and routing half does not. " + NOT_SET_HINT,
            whatToDo=set_fix("DT_PLATFORM_BASE", PLATFORM_EXAMPLE) + set_fix(
                "DT_PLATFORM_TOKEN", f"a platform token with {' + '.join(PLATFORM_SCOPES)}"
            ) + ["Or migrate the capture settings alone with `apply --capture-only`."],
        )
    try:
        base_url = normalise_base(base, expect_apps_host=True, label="DT_PLATFORM_BASE")
        make_client(base_url, f"Bearer {token}", timeout=timeout).get_json(
            PLATFORM_SETTINGS_OBJECTS,
            {"schema-id": OPENPIPELINE_ROUTING_SCHEMA, "scope": OPENPIPELINE_SCOPE},
        )
    except UsageError as exc:
        return _gate("platform", "warn", str(exc), whatToDo=exc.what_to_do)
    except ApiError as exc:
        return _gate(
            "platform", "warn",
            "DT_PLATFORM_TOKEN could not read the OpenPipeline routing object; the pipeline half "
            f"needs settings:objects:read and settings:objects:write. {exc.message}",
            error=exc.as_dict(),
            whatToDo=exc.what_to_do + [
                "Or migrate the capture settings alone with `apply --capture-only`."
            ],
        )
    host = urllib.parse.urlsplit(base_url).netloc
    return _gate("platform", "ok", f"the routing object on {host} is readable", host=host)


def _enablement_gate(client: HttpClient, app_id: str) -> Dict[str, Any]:
    try:
        payload = client.get_json(
            EFFECTIVE_VALUES, {"schemaIds": ENABLEMENT_SCHEMA, "scope": app_id}
        )
    except ApiError as exc:
        return _gate("new-rum", "unknown", f"{ENABLEMENT_SCHEMA} could not be read: {exc.message}",
                     error=exc.as_dict(), whatToDo=exc.what_to_do)
    items = (payload.get("items") if isinstance(payload, dict) else None) or [{}]
    first = items[0] if isinstance(items[0], dict) else {}
    rum = (first.get("value") or {}).get("rum") or {}
    origin = first.get("origin")
    if rum.get("enabled") and rum.get("enabledOnGrail"):
        return _gate("new-rum", "ok", f"enabled (effective value set on {origin})")
    return _gate(
        "new-rum", "block",
        f"New RUM is not enabled for this application (effective value set on {origin}). "
        "Enable it while RUM Classic is still active, then run preflight again.",
        whatToDo=[
            f"Ask the user to enable New RUM for {app_id} ({ENABLEMENT_SCHEMA}: `rum.enabled` "
            "and `rum.enabledOnGrail`), keeping RUM Classic on, then run "
            f"`preflight --application {app_id}` again."
        ],
    )


def _javascript_gate(client: HttpClient, app_id: str) -> Dict[str, Any]:
    minimum = f"{MIN_RUM_JAVASCRIPT[0]}.{MIN_RUM_JAVASCRIPT[1]}"
    ask = (f"Ask which RUM JavaScript version the pages load: below {minimum} the migrated "
           "properties capture nothing.")
    try:
        tag = client.get_text(f"{JAVASCRIPT_TAG}/{urllib.parse.quote(app_id, safe='')}")
    except ApiError as exc:
        return _gate(
            "rum-javascript", "unknown",
            f"the agent tag could not be read ({exc.status}; the scope is "
            f"rumManualInsertionTags.read). {ask}",
            error=exc.as_dict(),
            whatToDo=[
                "Add rumManualInsertionTags.read to DT_CLASSIC_TOKEN and run preflight again.",
                f"Or ask the user which RUM JavaScript version the pages load; at {minimum} or "
                "above, carry on.",
            ],
        )
    version = rum_javascript_version(tag)
    if version is None:
        return _gate(
            "rum-javascript", "unknown", f"the agent tag names no version. {ask}",
            whatToDo=[f"Ask the user which RUM JavaScript version the pages load; at {minimum} "
                      "or above, carry on."],
        )
    if _version_tuple(version) < MIN_RUM_JAVASCRIPT:
        # Not a block: the configuration transfers correctly and captures the moment the tag is
        # updated. What must not happen is reading the empty result as a failed migration.
        return _gate(
            "rum-javascript", "warn",
            f"the tag loads {version}, below {minimum}. The configuration transfers and captures "
            "nothing until the tag is updated. Say so before apply; afterwards an empty result "
            "is a version problem -- update the tag, do not migrate again.",
            version=version,
            whatToDo=[
                f"Tell the user before `apply`: the pages need RUM JavaScript {minimum} or "
                "above for the migrated properties to capture. Carrying on is safe."
            ],
        )
    return _gate("rum-javascript", "ok", f"the tag loads {version}", version=version)


def application_gates(client: HttpClient, app_id: str) -> Dict[str, Any]:
    """Exists, New RUM on, agent version high enough. Each read stands on its own."""
    kind = kind_for_id(app_id)
    result: Dict[str, Any] = {"id": app_id, "kind": kind, "name": None, "gates": []}
    gates: List[Dict[str, Any]] = result["gates"]
    if kind is None:
        gates.append(_gate(
            "application", "block", f"{app_id} is not a classic application id",
            whatToDo=["Pass a classic entity id such as APPLICATION-0123456789ABCDEF or "
                      "MOBILE_APPLICATION-0123456789ABCDEF; `scan --all` lists them."],
        ))
        return result
    try:
        app = read_application(client, kind, app_id)
    except ApiError as exc:
        gates.append(_gate(
            "application", "block",
            f"{app_id} could not be read ({exc.status}). A 404 is a wrong id or the wrong "
            "tenant; a 403 is a token without ReadConfig.",
            error=exc.as_dict(),
            whatToDo=exc.what_to_do,
        ))
        return result
    result["name"] = app.get("name")
    gates.append(_gate("application", "ok", "readable with ReadConfig"))
    if kind != "web":
        # The enablement schema and the tag endpoint are web-only; a mobile application's SDK
        # version is in the app binary, which no API reports.
        gates.append(_gate(
            "rum-javascript", "unknown", "mobile: the SDK version is in the app",
            whatToDo=["Nothing to check here: carry on. The mobile SDK version is not visible "
                      "through any API."],
        ))
        return result
    gates.append(_enablement_gate(client, app_id))
    gates.append(_javascript_gate(client, app_id))
    return result


def preflight_artifact(
    *,
    host: str,
    sources: Dict[str, str],
    gates: List[Dict[str, Any]],
    applications: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    checked = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "artifact": "preflight",
        "tool": TOOL_NAME,
        "toolVersion": TOOL_VERSION,
        "checkedAt": checked,
        "environment": {"classicHost": host},
        "settingsFrom": sources,
        "gates": gates,
        "applications": applications,
    }


def _blocked_gates(artifact: Dict[str, Any], app_ids: Optional[Iterable[str]] = None) -> List[str]:
    """Names of the blocking gates: the tenant-wide ones, and those of the named applications."""
    wanted = None if app_ids is None else set(app_ids)
    names = [g["gate"] for g in artifact.get("gates") or [] if g.get("status") == "block"]
    for app in artifact.get("applications") or []:
        if wanted is not None and app.get("id") not in wanted:
            continue
        names.extend(f"{app.get('id')}:{g['gate']}" for g in app.get("gates") or []
                     if g.get("status") == "block")
    return names


def summarise_preflight(artifact: Dict[str, Any]) -> Dict[str, Any]:
    host = artifact["environment"]["classicHost"]
    every = list(artifact["gates"]) + [g for app in artifact["applications"] for g in app["gates"]]
    by_status: Dict[str, int] = {}
    for gate in every:
        by_status[gate["status"]] = by_status.get(gate["status"], 0) + 1
    blocked = _blocked_gates(artifact)
    attention = by_status.get("warn", 0) + by_status.get("unknown", 0)
    summary: Dict[str, Any] = {
        "command": "preflight",
        "confirmHost": CONFIRM_HOST.format(
            host=host, source=artifact["settingsFrom"].get("DT_CLASSIC_BASE")
        ),
        "tenant": host,
        "settingsFrom": artifact["settingsFrom"],
        "gatesByStatus": by_status,
        "gates": artifact["gates"],
        "applications": artifact["applications"],
    }
    if blocked:
        summary["nextStep"] = (
            f"{len(blocked)} gate(s) block the migration ({', '.join(blocked)}); each says why, "
            "and its `whatToDo` says what to do. Tell the user, act on them, and run preflight "
            "again. Do not work around a blocked gate by hand."
        )
    elif not artifact["applications"]:
        summary["nextStep"] = (
            "The tenant and the credentials check out. Run `scan` to list the applications, then "
            "`preflight --application ENTITY_ID` for the ones chosen -- `apply` requires a "
            "preflight that covers them."
        )
    else:
        summary["nextStep"] = (
            "Nothing blocks. Confirm the host with the user"
            + (f", tell them each of the {attention} warn/unknown gate(s) in your own words "
               "and what its `whatToDo` asks of them"
               if attention else "")
            + ", then run `scan --application ENTITY_ID` for the same applications."
        )
    return summary


def load_preflight(out_dir: Path) -> Optional[Dict[str, Any]]:
    path = out_dir / PREFLIGHT_FILENAME
    if not path.is_file():
        return None
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(artifact, dict) and artifact.get("artifact") == "preflight":
        return artifact
    return None


def require_preflight(
    out_dir: Path, *, host: str, app_ids: Iterable[str], now: Optional[datetime] = None
) -> None:
    """`apply` writes only after a preflight of this tenant, recent, covering what it writes."""
    app_ids = sorted(set(app_ids))
    command = f"preflight --out-dir {out_dir} " + " ".join(f"--application {i}" for i in app_ids)
    run = f"Run `{command}` first."
    fix = [f"Run `{command}`, then this command again."]
    preflight = load_preflight(out_dir)
    if preflight is None:
        raise UsageError(f"no {PREFLIGHT_FILENAME} in {out_dir}. `apply` writes to a tenant only "
                         f"after preflight has checked it. {run}", fix=fix)
    checked_host = str((preflight.get("environment") or {}).get("classicHost") or "")
    if checked_host != host:
        raise UsageError(
            f"{PREFLIGHT_FILENAME} checked {checked_host or 'an unknown tenant'} and this run "
            f"talks to {host}. Check DT_CLASSIC_BASE. {run}",
            fix=fix + ([f"Or set DT_CLASSIC_BASE to https://{checked_host} if that is the tenant "
                        "the user confirmed."] if checked_host else []),
        )
    try:
        checked = datetime.strptime(str(preflight.get("checkedAt")), "%Y-%m-%dT%H:%M:%SZ")
        age = (now or datetime.now(timezone.utc)) - checked.replace(tzinfo=timezone.utc)
    except ValueError:
        age = None
    if age is None or age.total_seconds() > PREFLIGHT_MAX_AGE_HOURS * 3600:
        raise UsageError(f"{PREFLIGHT_FILENAME} is more than {PREFLIGHT_MAX_AGE_HOURS} hours old. "
                         f"{run}", fix=fix)
    wanted = set(app_ids)
    covered = {app.get("id") for app in preflight.get("applications") or []}
    missing = sorted(wanted - covered)
    if missing:
        raise UsageError(f"{PREFLIGHT_FILENAME} does not cover {', '.join(missing)}. {run}",
                         fix=fix)
    blocked = _blocked_gates(preflight, wanted)
    if blocked:
        raise UsageError(
            f"{PREFLIGHT_FILENAME} has blocking gates ({', '.join(blocked)}). Fix them and run "
            "preflight again; `apply` does not write past a block.",
            fix=[
                f"Act on each blocked gate's `whatToDo` in {out_dir / PREFLIGHT_FILENAME}, then "
                f"run `{command}` and this command again."
            ],
        )


def refuse_other_tenant(environment: Any, path: Path, *, host: str) -> None:
    """An artifact records the tenant it was made on; acting on it on another one is refused."""
    made_on = str((environment if isinstance(environment, dict) else {}).get("classicHost") or "")
    if made_on and made_on != host:
        raise UsageError(
            f"{path} was made on {made_on} and this run talks to {host}. Acting on it here would "
            "apply one tenant's configuration to another. Check DT_CLASSIC_BASE.",
            fix=[
                f"Set DT_CLASSIC_BASE to https://{made_on} if that is the tenant the user "
                "confirmed.",
                f"Or start over on {host} with `preflight`, `scan` and `plan`, in an --out-dir "
                "of its own.",
            ],
        )


def command_preflight(args: argparse.Namespace) -> int:
    if not str(args.out_dir).strip():
        raise UsageError(
            "--out-dir is empty. It is usually an unset shell variable; name the directory "
            "explicitly.",
            fix=FIX_OUT_DIR,
        )
    config_path = Path(args.config) if args.config else None
    sources = settings_sources(config_path=config_path)
    settings = load_settings(config_path=config_path)
    client = classic_client(settings, timeout=args.timeout)
    host = classic_host(settings)
    app_ids, resolved = resolve_applications(client, args.application)

    gates = [schema_gate(client)]
    write_scope = next((app_id for app_id in app_ids if kind_for_id(app_id) == "web"), None)
    if write_scope:
        gates.append(write_gate(client, write_scope))
    else:
        gates.append(_gate(
            "settings-write", "unknown",
            "checked once a web application is named with --application",
            whatToDo=["Run `preflight --application APPLICATION-…` naming the applications "
                      "to migrate."],
        ))
    gates.append(platform_gate(settings, timeout=args.timeout))
    applications = [application_gates(client, app_id) for app_id in app_ids]

    artifact = preflight_artifact(host=host, sources=sources, gates=gates, applications=applications)
    path = write_artifact(Path(args.out_dir), PREFLIGHT_FILENAME, artifact)
    summary = summarise_preflight(artifact)
    summary["artifact"] = str(path)
    summary["status"] = "blocked" if summary["gatesByStatus"].get("block") else "ok"
    if resolved:
        summary["resolvedNames"] = resolved
    preflight_guide(summary)
    print(json.dumps(summary, indent=2))
    return EXIT_PARTIAL if summary["status"] == "blocked" else EXIT_OK


# ----------------------------------------------------------- the guide, in the output

# What the reference says to read and to say, carried in the output that is read anyway. The
# reference files ship one directory above this script, under `references/`; a section is its
# heading as written there, so it can be found by search as well as by anchor.
READ = {
    "prerequisites": ("prerequisites-and-limits.md", "Prerequisites"),
    "inventory": (
        "running-the-migration.md", "Step 2 — Inventory, then read only what the user chooses"
    ),
    "classify": ("classifying-properties.md", "Step 3 — Classify and translate"),
    "present": ("running-the-migration.md", "Step 4 — Present the plan and stop"),
    "row2": (
        "session-scoped-properties.md",
        "Choose per property, for a configured session-scoped property (row 2)",
    ),
    "carrier": ("session-scoped-properties.md", "Remove the carrier event property, or keep it"),
    "user-tags": ("user-tagging.md", "What migrates, and what changes"),
    "lost": ("classifying-properties.md", "What you lose, and what to do instead"),
    "apply": ("writing-the-objects.md", "Step 5 — Apply"),
    "verify": ("verifying-the-migration.md", "The four layers"),
    "handoff": ("running-the-migration.md", "Step 7 — Hand off the code changes"),
}

# Where the reference explains an expression this tool leaves to you, by rule.
EXPRESSION_READ = {"cleanup": "lost", USER_TAG_RULE: "user-tags"}

NOT_GENERATED = (
    "Not generated, because this classic rule has no exact translation (`why`). An expression "
    "that is nearly right migrates the value wrongly instead of not at all, and nothing "
    "downstream reports it. Write one that yields what `source` extracted -- and the value "
    "unchanged where it matched nothing, as classic kept it -- confirm it with the user, and "
    "pass it with `supplyWith`."
)


def read_first(*names: str) -> List[Dict[str, str]]:
    unique = list(dict.fromkeys(names))
    return [{"file": f"references/{READ[name][0]}", "section": READ[name][1]} for name in unique]


def expression_guide(rule: Any) -> Dict[str, Any]:
    """What a `needsYourExpression` entry adds: why it is yours, and where to read up on it."""
    return {
        "notGenerated": NOT_GENERATED,
        "readFirst": read_first(EXPRESSION_READ.get(str(rule or ""), "classify")),
    }


def cli(command: str, out_dir: Any, *flags: str) -> str:
    """A command as it is run, with the --out-dir it was run with -- never a placeholder dir."""
    return " ".join([command, "--out-dir", str(out_dir), *flags])


def approval(command: str, why: str) -> Dict[str, Any]:
    return {"required": True, "command": command, "why": why}


def guide(
    summary: Dict[str, Any],
    *,
    read: Iterable[str],
    tell: Iterable[str] = (),
    approve: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """The same three fields on every summary, so none of them is a thing to look for."""
    summary["readFirst"] = read_first(*read)
    summary["tellTheUser"] = list(tell)
    summary["needsApproval"] = approve or {"required": False}
    return summary


def _properties(count: int) -> str:
    return f"{count} propert{'y' if count == 1 else 'ies'}"


def preflight_guide(summary: Dict[str, Any]) -> Dict[str, Any]:
    every = list(summary["gates"]) + [g for app in summary["applications"] for g in app["gates"]]
    attention = [
        f"{gate['gate']}: {gate['detail']}" for gate in every if gate["status"] in ("warn", "unknown")
    ]
    return guide(summary, read=["prerequisites"], tell=[summary["confirmHost"], *attention])


def inventory_guide(summary: Dict[str, Any]) -> Dict[str, Any]:
    return guide(
        summary,
        read=["inventory"],
        tell=[
            f"{summary['applications']} applications were found. Which of them carry properties "
            "has not been checked, because that is one request per application, "
            f"{human_duration(summary.get('estimatedSweepSeconds'))} for all of them."
        ],
    )


def scan_guide(summary: Dict[str, Any], out_dir: Any) -> Dict[str, Any]:
    tell = []
    if summary["sessionScopedProperties"]:
        tell.append(
            f"{_properties(summary['sessionScopedProperties'])} classic stored on the session. "
            "Latest Dynatrace captures on events only, so the plan asks how to keep each: "
            f"{_choices_in_words()}."
        )
    if "nextStep" not in summary and summary["status"] == "ok":
        summary["nextStep"] = f"Run `{cli('plan', out_dir)}`."
    return guide(summary, read=["classify"], tell=tell)


def plan_guide(summary: Dict[str, Any], payload: Dict[str, Any], out_dir: Any) -> Dict[str, Any]:
    """Step 4 as output: what to open, what to say, and the one write that follows a yes."""
    flags = summary["flags"]
    read, tell = ["present"], []
    if summary["decisionsPending"]:
        read.append("row2")
        tell.append(
            f"{_properties(summary['decisionsPending'])} classic stored on the session need a "
            f"choice of how to keep them: {_choices_in_words()}. The pipeline rule is "
            "recommended: it needs no code change."
        )
    if summary["decisionsPending"] or summary["row2Defaulted"]:
        summary["ifTheUserChooses"] = session_choice_commands(out_dir)
    if summary["row2Defaulted"]:
        read.append("row2")
        tell.append(row2_default_statement(summary["row2Defaulted"]))
    if summary["applicationsWithUserTagging"]:
        read.append("user-tags")
        tell.append(
            "Classic user tagging has no setting in Latest Dynatrace. Each tag becomes a captured "
            "event property, and one pipeline statement per application copies it into "
            "`user.identifier`."
        )
        if flags.get("last-action-wins-is-free"):
            tell.append(
                "The session-level tag behaves as before: on both platforms the last user action "
                "in a session that carries a tag decides the session's tag."
            )
        if flags.get("crop-lifted"):
            tell.append(
                f"Tags are no longer cropped at {CLASSIC_USER_TAG_CROP} characters. Anything that "
                "matched the cropped form -- a filter, a segment, an alert, an export -- has to "
                "be checked."
            )
    if summary["applicationsLosingAllUserTagging"]:
        tell.append(summary["userTaggingWarning"])
    target = summary.get("pipelineTarget")
    if target and target["mode"] == "new":
        tell.append(
            f"The pipeline `{target['pipelineId']}` does nothing until a route sends events to "
            "it. The migration writes both, and puts the route first in the shared routing "
            "object, because the first matching route wins."
        )
    elif target:
        tell.append(
            f"The processors join `{target['pipelineId']}` and see only what its routes already "
            "send it. Routing is not changed."
        )
    if summary["eventPropertyCarriersKept"]:
        read.append("carrier")
        summary["removeTheEventPropertyWith"] = (
            "Only after verify has passed and the user says yes: re-run this plan with the same "
            "choices plus --drop-event-property (or --drop-event-property-key <classic key>=yes "
            "for one), then report and apply as before."
        )
        tell.append(
            f"{_properties(summary['eventPropertyCarriersKept'])} will exist twice: on the "
            "session, and as the event property the pipeline read it from, which classic never "
            "had. Removing the event property is recommended after the promotion has been "
            "verified, as a second change; it breaks anything still reading it."
        )
    if flags.get("privacy-regression"):
        read.append("lost")
        tell.append(
            f"{_properties(flags['privacy-regression'])} classic suppressed for visitors who "
            "signal Do-Not-Track. Latest Dynatrace has no such control, so migrated as-is they "
            "are captured for everyone. The choice is masking for every visitor, or not "
            "migrating them."
        )
    if summary["blocked"] or summary["userTagsBlocked"]:
        read.append("lost")
        tell.append(
            f"{summary['blocked'] + summary['userTagsBlocked']} item(s) cannot migrate. For "
            "each, the plan says what would have to change: the source, the platform, or the "
            "translation."
        )
    if summary["keysChanged"]:
        tell.append(
            f"{summary['keysChanged']} key(s) change. A key cannot be reused while its old data "
            "is retained, so a rename is close to irreversible."
        )
    if summary["codeChanges"]:
        tell.append(
            f"{_properties(summary['codeChanges'])} need a code change. The plan lists them, "
            "each with the call that sends it."
        )
    translated = flags.get("cleanup-rule-translated", 0)
    if translated:
        tell.append(
            f"{translated} classic cleanup {_rules_are(translated)} translated into pipeline "
            "rules that extract the same part of the value. Where a rule matches nothing, the value is kept "
            "as captured, as classic kept it."
        )
    folded = flags.get("ignore-case-lost", 0)
    if folded:
        tell.append(
            f"{_properties(folded)} classic stored in lower case. Latest Dynatrace keeps the "
            "case as captured, so a filter or comparison that expects lower case has to fold "
            "it -- in the query, or with a pipeline rule."
        )
    expressions = payload["needsYourExpression"]
    if expressions:
        read.extend(EXPRESSION_READ.get(str(entry.get("rule")), "classify") for entry in expressions)
        tell.append(
            f"{len(expressions)} classic cleanup {_rules_have(len(expressions))} no exact translation. Each needs "
            "a DQL expression that does the same, written and confirmed with you; until then "
            "only the capture settings can be written, not the pipeline."
        )
        summary["expressionsNeeded"] = (
            "openpipeline-payload.json `needsYourExpression` says why for each; pass each "
            "confirmed expression with its `supplyWith`."
        )
    approve = None
    if not summary["decisionsPending"]:
        approve = plan_approval(payload, out_dir)
        summary.setdefault(
            "nextStep",
            f"Run `{cli('report', out_dir)}` and present plan-report.md as written, say each "
            "`tellTheUser` statement, and stop. Run `needsApproval.command` only on the user's yes.",
        )
    return guide(summary, read=read, tell=tell, approve=approve)


def _rules_are(count: int) -> str:
    return "rule is" if count == 1 else "rules are"


def _rules_have(count: int) -> str:
    return "rule has" if count == 1 else "rules have"


def _choices_in_words() -> str:
    return (f"{ROW_2_LABELS['A']} (nothing to deploy), {ROW_2_LABELS['B']} (a release), or "
            f"{ROW_2_LABELS['C']} (no code change)")


def session_choice_commands(out_dir: Any) -> Dict[str, Any]:
    """For the agent: which re-run each answer means. The user hears the labels, never these."""
    return {
        "all": {ROW_2_LABELS[letter]: cli("plan", out_dir, "--row2", letter)
                for letter in sorted(ROW_2_LABELS)},
        "oneProperty": "add --row2-key <classic key>=A|B|C per property; A is "
        f"{ROW_2_LABELS['A']}, B {ROW_2_LABELS['B']}, C {ROW_2_LABELS['C']}",
    }


def row2_default_statement(count: int) -> str:
    return (
        f"{_properties(count)} classic stored on the session {'stays' if count == 1 else 'stay'} "
        f"{ROW_2_LABELS['C']} -- the recommended way, with no code change. That means pipeline "
        "changes: a pipeline and the route to it, written after the capture settings. If "
        "pipeline changes are not wanted, the alternatives are "
        f"{ROW_2_LABELS['A']} (nothing to deploy) or {ROW_2_LABELS['B']} (a release)."
    )


def plan_approval(payload: Dict[str, Any], out_dir: Any) -> Dict[str, Any]:
    """The first write a decided plan leads to: `apply`, narrowed to the half that can run."""
    capture_only = bool(payload.get("problems") or payload.get("needsYourExpression"))
    return approval(
        cli("apply", out_dir, *(["--capture-only"] if capture_only else [])),
        "The first write to the tenant. Run it only on the user's yes to the plan as "
        "presented. The same command with --dry-run first writes nothing and records what "
        "would change."
        + (" With --capture-only the pipeline half stays to be created by hand from "
           "openpipeline-payload.json, and the migration is half-applied until it is."
           if capture_only else ""),
    )


def apply_flags(args: argparse.Namespace) -> List[str]:
    """The flags that select what an `apply` run covers, so a re-run covers the same."""
    flags = ["--plan", str(args.plan)] if args.plan else []
    for app_id in args.application or []:
        flags += ["--application", app_id]
    if args.overwrite_existing:
        flags.append("--overwrite-existing")
    if args.capture_only:
        flags.append("--capture-only")
    if args.pipeline_only:
        flags.append("--pipeline-only")
    return flags


HALF_IN_WORDS = {"capture": "capture settings", "pipeline": "pipeline and its route"}


def apply_guide(summary: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    tell = [summary["halfApplied"]] if summary.get("halfApplied") else []
    if summary.get("remainingHalf"):
        summary["completeWith"] = cli("apply", args.out_dir, f"--{summary['remainingHalf']}-only")
    if summary["dryRun"]:
        return guide(
            summary,
            read=["apply"],
            tell=tell,
            approve=approval(
                cli("apply", args.out_dir, *apply_flags(args)),
                "This run wrote nothing; apply-dry-run.json says what would change. Show the "
                "user, and run this only on their yes.",
            ),
        )
    tell.append(
        "The configuration is written. Data shows the change only once traffic arrives: the "
        "configuration is checked now, and the queries that confirm the data are handed over "
        "to run later."
    )
    if summary.get("backup"):
        tell.append(
            "The configuration as it was before is saved, and the migration can be undone from it."
        )
        restore = cli("restore", args.out_dir, "--backup", summary["backup"], "--dry-run")
        summary["undo"] = (
            f"Only when the user asks to undo: `{restore}`, show what it would change, and run "
            "it without --dry-run on their yes."
        )
    if summary["status"] == "ok":
        summary.setdefault("nextStep", f"Run `{cli('verify', args.out_dir, '--notebook')}`.")
    return guide(summary, read=["verify"], tell=tell)


def verify_guide(summary: Dict[str, Any]) -> Dict[str, Any]:
    tell = [
        "The configuration read-back is the pass or fail. The queries need traffic: run them "
        "once data has arrived -- no data yet is not a failure."
    ]
    if summary["status"] == "ok":
        summary.setdefault(
            "nextStep",
            "Hand the code changes over: code-changes.json lists each property with its classic "
            "capture expression beside it.",
        )
    return guide(summary, read=["verify", "handoff"], tell=tell)


def restore_guide(summary: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    if not summary["dryRun"]:
        return guide(summary, read=["apply"])
    flags = ["--backup", summary["backup"]]
    for app_id in args.application or []:
        flags += ["--application", app_id]
    if args.capture_only:
        flags.append("--capture-only")
    if args.pipeline_only:
        flags.append("--pipeline-only")
    return guide(
        summary,
        read=["apply"],
        approve=approval(
            cli("restore", args.out_dir, *flags),
            "This run wrote nothing; restore-dry-run.json says what would change. Show the "
            "user, and run this only on their yes.",
        ),
    )


# ----------------------------------------------------------------------------- report

# The layer that blocks a property, per the reference: the **source** (nothing in the browser
# to read, or a classic definition that reads nothing today), the **platform** (a limit it
# refuses, or support it does not have yet), or the **translation** (a recipe with no
# equivalent). The layer is what tells the user whether anything they could change unblocks it.
BLOCKING_LAYER = {
    "request-attribute-unsupported": "source",
    "unresolved-capture-setting": "source",
    "missing-key": "source",
    "missing-capture-expression": "source",
    "empty-expression-segment": "source",
    "quoted-bracket-notation": "source",
    "json-parser-first": "source",
    "charset-rejected": "platform",
    "key-too-long": "platform",
    "prefix-embedded": "platform",
    "key-collision": "platform",
    "capture-type-blocked-by-layer": "platform",
    "capture-type-unsupported": "translation",
    "capture-type-unknown": "translation",
    "selector-text-content": "translation",
    "capture-needs-its-own-rule": "translation",
}

# Twenty session properties per application at no additional cost; past that, each one bills
# for every session it appears in.
FREE_SESSION_PROPERTIES = 20

REPORT_FILENAME = "plan-report.md"


def blocking_layer(item: Dict[str, Any]) -> str:
    """`source`, `platform` or `translation` -- `unknown` only for an origin this build lacks."""
    if item.get("row") == 5:
        return "source"
    names = [flag["flag"] for flag in item.get("flags") or [] if flag.get("blocking")]
    names.append(str(item.get("blockedReason") or item.get("reason") or ""))
    return next((BLOCKING_LAYER[name] for name in names if name in BLOCKING_LAYER), "unknown")


def blocking_detail(item: Dict[str, Any]) -> str:
    detail = next(
        (flag["detail"] for flag in item.get("flags") or [] if flag.get("blocking")), None
    )
    return str(detail or item.get("blockedReason") or item.get("reason") or "no equivalent")


def _session_properties_after(app: Dict[str, Any]) -> int:
    """Session properties the plan leaves this application with: what is billed past 20."""
    count = 0
    for row in app["properties"]:
        if row["blocked"] or not row["sessionScoped"]:
            continue
        chosen = (row.get("decision") or {}).get("chosen")
        if row["row"] == 2 and chosen not in ("B", "C"):
            continue
        count += 1
    return count


# What each classic capture type reads, in the words of whoever configured it.
CAPTURE_TYPE_WORDS = {
    "COOKIE": "cookie",
    "CSS_SELECTOR": "CSS selector",
    "JAVA_SCRIPT_FUNCTION": "JavaScript function",
    "JAVA_SCRIPT_VARIABLE": "JavaScript variable",
    "META_TAG": "meta tag",
    "QUERY_STRING": "query-string parameter",
    "RESPONSE_HEADER": "response header",
}

# Said once in a section of its own, so not repeated for every property it applies to.
SAID_ELSEWHERE = frozenset({"event-property-kept-beside-the-session-property"})

# The report is the page the user reads. It names what happens and what they can choose --
# never a decision-table row, an option letter, a flag code or a CLI flag. Those are the
# agent's, and they stay in the JSON.


def _sentence(text: Any) -> str:
    text = str(text).strip()
    text = text[:1].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def _capitalised(text: str) -> str:
    return text[:1].upper() + text[1:]


def _how_it_migrates(row: Dict[str, Any]) -> str:
    if row["row"] == 2:
        chosen = (row.get("decision") or {}).get("chosen")
        return _capitalised(ROW_2_LABELS[chosen]) if chosen else "**Needs your choice**"
    if row["codeChange"]:
        return "Sent by your code: needs a code change"
    return "Captured automatically"


def _report_properties(app: Dict[str, Any]) -> List[str]:
    lines = [
        "| Property | Classic scope | How it migrates |",
        "|---|---|---|",
    ]
    for row in app["properties"]:
        if row["blocked"]:
            continue
        name = f"`{_escape_cell(row['key'])}`"
        if row["keyChanged"]:
            name += f" (was `{_escape_cell(row['classicKey'])}`)"
        lines.append(
            f"| {name} | {'session' if row['sessionScoped'] else 'user action'} "
            f"| {_escape_cell(_how_it_migrates(row))} |"
        )
    return lines if len(lines) > 2 else ["No property migrates."]


def _report_row2(app: Dict[str, Any]) -> List[str]:
    rows = [row for row in app["properties"] if row.get("decision")]
    if not rows:
        return []
    defaulted = [row for row in rows if row["decision"].get("defaulted")]
    lines = [
        "",
        "### Properties classic kept on the session",
        "",
        "Latest Dynatrace captures these on events, so each is kept one of three ways:",
        "",
    ]
    for letter in (ROW2_DEFAULT, *sorted(set(ROW_2_LABELS) - {ROW2_DEFAULT})):
        recommended = " (recommended)" if letter == ROW2_DEFAULT else ""
        lines.append(f"- **{_capitalised(ROW_2_LABELS[letter])}**{recommended}: "
                     f"{ROW_2_OPTIONS[letter]}")
    if defaulted:
        lines += [
            "",
            f"{_properties(len(defaulted))} {'is' if len(defaulted) == 1 else 'are'} planned the "
            "recommended way, with no code change. That means pipeline changes: a pipeline and "
            "its route, written after the capture settings. If you do not want pipeline "
            "changes, one of the other two is the alternative.",
        ]
    lines += ["", "| Property | Kept |", "|---|---|"]
    for row in rows:
        chosen = row["decision"]["chosen"]
        shown = _capitalised(ROW_2_LABELS[chosen]) if chosen else "**needs your choice**"
        if row["decision"].get("defaulted"):
            shown += " (recommended)"
        lines.append(f"| `{_escape_cell(row['key'])}` | {shown} |")
    return lines


def _report_user_tags(app: Dict[str, Any]) -> List[str]:
    planned = app.get("userTags") or {}
    tags = planned.get("tags") or []
    if not tags:
        return []
    migrating = planned.get("migrating") or []
    lines = [
        "",
        "### User tags",
        "",
        "Classic user tagging has no setting in Latest Dynatrace. Each tag becomes a captured "
        f"event property, and one pipeline statement copies the first one that has a value into "
        f"`{USER_TAG_FIELD}`, in this order:",
        "",
        "| Order | Reads | Stored as |",
        "|---|---|---|",
    ]
    by_index = {tag["index"]: tag for tag in tags}
    changes = []
    for position, index in enumerate(migrating, start=1):
        tag = by_index[index]
        capture = tag.get("capture") or {}
        kind = CAPTURE_TYPE_WORDS.get(str(capture.get("type")), str(capture.get("type")))
        lines.append(
            f"| {position} | {_escape_cell(kind)} `{_escape_cell(capture.get('capturingName'))}` "
            f"| `{_escape_cell(tag['key'])}` |"
        )
        if tag.get("reusesCaptureOf"):
            changes.append(f"- Tag {position}: shares the capture of "
                           f"`{_escape_cell(tag['reusesCaptureOf'])}`.")
        changes += [f"- Tag {position}: {_sentence(flag['detail'])}"
                    for flag in tag["flags"] if not flag.get("blocking")]
    if not migrating:
        lines.append("| — | **none** | every tag is blocked: nothing sets a user identifier |")
    notes = [f"- {_sentence(note['detail'])}" for note in planned.get("notes") or []]
    if changes or notes:
        lines.append("")
    return lines + changes + notes


def _report_blocked(app: Dict[str, Any]) -> List[str]:
    entries = [
        (f"`{row['classicKey']}`", row) for row in app["properties"] if row["blocked"]
    ] + [
        (f"user tag {tag['index'] + 1}", tag)
        for tag in (app.get("userTags") or {}).get("tags") or []
        if tag["blocked"]
    ]
    if not entries:
        return []
    lines = [
        "",
        "### Cannot migrate",
        "",
        "The layer says what would have to change: the **source** (nothing to read, or a "
        "classic definition that reads nothing today), the **platform** (a limit it refuses) or "
        "the **translation** (no equivalent recipe).",
        "",
        "| Item | Layer | Why |",
        "|---|---|---|",
    ]
    for name, item in entries:
        lines.append(
            f"| {_escape_cell(name)} | {blocking_layer(item)} | {_escape_cell(blocking_detail(item))} |"
        )
    return lines


def _report_code_changes(app: Dict[str, Any]) -> List[str]:
    changes = code_change_list(app)
    if not changes:
        return []
    lines = ["", "### Code changes", "",
             "Nothing captures these automatically any more; your code sends them.", ""]
    for change in changes:
        line = f"- `{_escape_cell(change['key'])}`: {_capitalised(change['replace'])}."
        capture = change["classicCapture"] or {}
        if capture:
            kind = CAPTURE_TYPE_WORDS.get(str(capture.get("type")), str(capture.get("type")))
            line += (f" Classic read the {kind} `{_escape_cell(capture.get('capturingName'))}`; "
                     "your code decides when to send it.")
        lines.append(line)
    return lines


def _report_changes(app: Dict[str, Any]) -> List[str]:
    """Every change a property's plan carries, in full -- not the few someone thought to pick."""
    lines = [
        f"- `{_escape_cell(row['key'])}`: {_sentence(flag['detail'])}"
        for row in app["properties"]
        if not row["blocked"]
        for flag in row["flags"]
        if not flag.get("blocking") and flag["flag"] not in SAID_ELSEWHERE
    ]
    return ["", "### What changes", "", *lines] if lines else []


def plan_report_markdown(
    plan: Dict[str, Any], payload: Dict[str, Any], summary: Dict[str, Any], out_dir: Any
) -> str:
    """Step 4, as the page the user reads. Every line is derived from the plan."""
    source = plan.get("source") or {}
    lines = [
        "# RUM property migration plan",
        "",
        f"Tenant `{(source.get('environment') or {}).get('classicHost')}`, scanned "
        f"{source.get('scannedAt')}, planned {plan.get('plannedAt')}. Nothing has been written "
        "to the tenant.",
    ]
    for app in plan["applications"]:
        sessions = _session_properties_after(app)
        lines += [
            "",
            f"## {_escape_cell(app.get('name') or app['id'])} (`{app['id']}`)",
            "",
            f"{_properties(len(app['properties']))}; {sessions} of them session-scoped after the "
            f"migration, against {FREE_SESSION_PROPERTIES} at no additional cost per application"
            + (f" -- **{sessions - FREE_SESSION_PROPERTIES} beyond that are billed** for every "
               "session they appear in." if sessions > FREE_SESSION_PROPERTIES else "."),
            "",
            *_report_properties(app),
            *_report_row2(app),
            *_report_code_changes(app),
            *_report_user_tags(app),
            *_report_changes(app),
            *_report_blocked(app),
        ]

    lines += ["", "## Cost", "",
              f"Up to {FREE_SESSION_PROPERTIES} session properties per application at no "
              "additional cost; each one past that bills for every session it appears in. A "
              "parallel run does not double-bill: only the larger of the classic and the new "
              "count is charged. The pipeline path is at worst cost-neutral, not free -- a "
              "promoted property is present in the session and counts like any other."]

    target = summary.get("pipelineTarget")
    if target:
        lines += ["", "## Pipeline", ""]
        if target["mode"] == "new":
            lines.append(
                f"The processors go into a new pipeline, `{target['pipelineId']}` "
                "(recommended): " + target["why"] + " It does nothing until a route sends "
                "events to it, so the migration writes the route too, first in the shared routing "
                "object. Who may change routing is granted separately from pipeline access; "
                "confirm it now."
            )
        else:
            lines.append(
                f"The processors join the existing pipeline `{target['pipelineId']}` and see "
                "only what its routes already send it. Routing is not changed."
            )
    if summary["eventPropertyCarriersKept"]:
        lines += ["", "## The event property beside each promoted one", "",
                  f"{_properties(summary['eventPropertyCarriersKept'])} will exist twice: on the "
                  "session, and as the event property the pipeline read it from, which classic "
                  "never had. Keeping it costs nothing and is the way to tell a broken capture "
                  "from a broken promotion. Removing it is recommended **after** the promotion "
                  "has been verified, as a second change; it breaks anything still reading "
                  "`event_properties.<key>`."]

    pending = []
    if summary["decisionsPending"]:
        pending.append(
            f"{_properties(summary['decisionsPending'])} classic kept on the session need your "
            "choice of how to keep them (above)."
        )
    for entry in payload.get("needsYourExpression") or []:
        why = f" ({entry['why']})" if entry.get("why") else ""
        pending.append(
            f"`{entry['key']}`: the classic cleanup rule `{entry['source']}` has no exact "
            f"translation{why}. It needs a DQL expression that does the same, written and "
            "confirmed with you; until then only the capture settings can be written."
        )
    for problem in payload.get("problems") or []:
        if not payload.get("needsYourExpression"):
            pending.append(f"Pipeline: {problem}.")
    if pending:
        lines += ["", "## Still open", ""] + [f"- {item}" for item in pending]

    lines += ["", "## Next", ""]
    approve = summary["needsApproval"]
    if approve["required"]:
        lines.append(
            "Nothing is written to the tenant until you say yes. A dry run can come first: it "
            "writes nothing and shows what would change."
        )
        if payload.get("problems") or payload.get("needsYourExpression"):
            lines += ["", "Only the capture settings can be written now. The pipeline waits for "
                      "what is still open above, and until it is written the migration is half "
                      "done."]
    else:
        lines.append("Nothing can be applied until what is open above is decided.")
    return "\n".join(lines) + "\n"


def command_report(args: argparse.Namespace) -> int:
    """`plan-report.md`: the plan as the page the user decides on. Reads local files only."""
    if not str(args.out_dir).strip():
        raise UsageError("--out-dir is empty. Name the directory `plan` wrote to.",
                         fix=FIX_OUT_DIR)
    out_dir = Path(args.out_dir)
    plan_path = Path(args.plan) if args.plan else out_dir / "plan.json"
    plan = load_plan_artifact(plan_path, phase="report")
    payload = openpipeline_payload(plan)
    summary = summarise_plan(plan)
    plan_guide(summary, payload, args.out_dir)
    report = plan_report_markdown(plan, payload, summary, args.out_dir)
    path = (out_dir / REPORT_FILENAME).resolve()
    path.write_text(report, encoding="utf-8")
    result: Dict[str, Any] = {
        "command": "report",
        "status": "decisions-pending" if summary["decisionsPending"] else "ok",
        "report": str(path),
        "nextStep": (
            f"Show {REPORT_FILENAME} to the user as written -- it is the plan, and it carries "
            "every statement `tellTheUser` lists -- and stop. "
            + ("Run `needsApproval.command` only on the user's yes."
               if summary["needsApproval"]["required"]
               else "Ask for what it lists under \"Still open\" and re-run `plan` with the answers.")
        ),
    }
    guide(result, read=["present"], tell=summary["tellTheUser"],
          approve=summary["needsApproval"] if summary["needsApproval"]["required"] else None)
    print(json.dumps(result, indent=2))
    return EXIT_OK


# ----------------------------------------------------------------------------- status

STATUS_ARTIFACTS = (
    "preflight.json", "inventory.json", "scan.json", "plan.json", "openpipeline-payload.json",
    "apply-dry-run.json", "apply.json", "verify.json", "restore-dry-run.json", "restore.json",
)
STAMP_FIELD = {
    "preflight": "checkedAt", "inventory": "listedAt", "scan": "scannedAt", "plan": "plannedAt",
    "apply": "appliedAt", "verify": "verifiedAt", "restore": "restoredAt",
}


def read_local(path: Path) -> Optional[Dict[str, Any]]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return artifact if isinstance(artifact, dict) else None


def _stamp(artifact: Optional[Dict[str, Any]]) -> str:
    return str((artifact or {}).get(STAMP_FIELD.get(str((artifact or {}).get("artifact")), "")) or "")


def _tenant_of(artifact: Dict[str, Any]) -> Optional[str]:
    env = artifact.get("environment") or (artifact.get("source") or {}).get("environment") or {}
    return env.get("classicHost") if isinstance(env, dict) else None


def _has_errors(artifact: Dict[str, Any]) -> bool:
    pipeline = artifact.get("pipeline") or {}
    return bool(pipeline.get("error")) or any(
        app.get("error") for app in artifact.get("applications") or []
    )


def status_next(found: Dict[str, Optional[Dict[str, Any]]], out_dir: str) -> Dict[str, Any]:
    """The one next command for an out-dir, from its artifacts alone. Talks to no tenant.

    `out_dir` is the directory as it was given, so the commands repeat it as written.
    """
    preflight, inventory = found["preflight.json"], found["inventory.json"]
    scan, plan = found["scan.json"], found["plan.json"]
    payload = found["openpipeline-payload.json"] or {}
    dry, applied = found["apply-dry-run.json"], found["apply.json"]
    verified, restored = found["verify.json"], found["restore.json"]
    pending: List[Dict[str, Any]] = []

    def step(command: Optional[str], why: str, read: List[str], approve: bool = False):
        return {
            "nextCommand": command,
            "nextStep": why,
            "read": read,
            "approve": approval(command, why) if approve and command else None,
            "pending": pending,
        }

    plan_ids = [app["id"] for app in (plan or {}).get("applications") or []]
    ids = plan_ids or [app["id"] for app in (scan or {}).get("applications") or []]
    preflight_command = cli("preflight", out_dir, *[f"--application {i}" for i in ids])

    if restored and _stamp(restored) >= _stamp(applied):
        return step(None, "The last run that wrote was `restore`: the tenant is back as its "
                    "backup found it. To migrate again, re-run `plan`, then `apply`.", ["apply"])
    if preflight is None:
        return step(preflight_command, "No preflight yet. It names the tenant and checks the "
                    "gates `apply` requires.", ["prerequisites"])
    blocked = _blocked_gates(preflight, ids or None)
    if blocked:
        pending.append({"item": "blocked-gates", "detail": ", ".join(blocked)})
        return step(preflight_command, f"preflight.json has blocking gates ({', '.join(blocked)}). "
                    "Act on each gate's `whatToDo` in preflight.json, then run preflight again.",
                    ["prerequisites"])
    if scan is None:
        if inventory is not None:
            return step(
                cli("scan", out_dir, "--application", "ENTITY_ID"),
                f"inventory.json lists {len(inventory.get('applications') or [])} applications, "
                "and which of them carry properties is unchecked. Ask the user which to migrate "
                "and name each with --application (repeatable), or use --all after saying how "
                "long the sweep takes.",
                ["inventory"],
            )
        return step(cli("scan", out_dir), "No scan yet.", ["inventory"])
    if plan is None or _stamp(plan) < _stamp(scan):
        return step(cli("plan", out_dir), "No plan from the latest scan.", ["classify"])

    planned = summarise_plan(plan)
    expressions = payload.get("needsYourExpression") or []
    if planned["decisionsPending"]:
        pending.append({"item": "row2", "detail": f"{_properties(planned['decisionsPending'])} "
                        "need A, B or C"})
    if expressions:
        pending.append({"item": "expressions", "detail": f"{len(expressions)} pipeline rule(s) "
                        "need an expression; only the capture half can be applied"})
    if planned["eventPropertyCarriersKept"]:
        pending.append({"item": "carrier", "detail": f"{_properties(planned['eventPropertyCarriersKept'])} "
                        "keep their event property; removing it is a second change, after verify"})
    if planned["row2Defaulted"]:
        pending.append({"item": "row2-default", "detail": f"{_properties(planned['row2Defaulted'])} "
                        "planned as C by default, which means pipeline changes; A or B if the "
                        "user does not want them"})
    if planned["decisionsPending"]:
        return step(cli("plan", out_dir), "Row 2 is undecided in this plan. Re-run `plan`: C is "
                    "the default, or pass --row2 A|B (--row2-key KEY=A|B per property) where "
                    "pipeline changes are not wanted.", ["row2"])

    capture_only = bool(expressions or payload.get("problems"))
    if applied is None or _stamp(applied) < _stamp(plan):
        try:
            require_preflight(Path(out_dir), host=str(_tenant_of(plan) or ""), app_ids=plan_ids)
        except UsageError as exc:
            return step(preflight_command, str(exc), ["prerequisites"])
        flags = ["--capture-only"] if capture_only else []
        if not found.get(REPORT_FILENAME):
            return step(cli("report", out_dir), "The plan is ready and has not been presented "
                        f"since it was made. `report` writes {REPORT_FILENAME}; show it as "
                        "written, then dry-run.", ["present"])
        if dry is None or _stamp(dry) < _stamp(plan):
            return step(cli("apply", out_dir, *flags, "--dry-run"),
                        "The plan is ready. Present it, say what `plan` lists under "
                        "`tellTheUser`, then run the dry run: it reads the tenant and writes "
                        "nothing.", ["present"])
        pending.append({"item": "approval", "detail": "the user's yes to the presented plan"})
        return step(cli("apply", out_dir, *flags), "The dry run is newer than the plan. This is "
                    "the first write: run it only on the user's yes.", ["apply"], approve=True)

    halves = applied.get("halves") or ["capture", "pipeline"]
    half_flags = [f"--{halves[0]}-only"] if len(halves) == 1 else []
    if _has_errors(applied):
        return step(cli("apply", out_dir, *half_flags), "apply.json records errors, each with "
                    "its `whatToDo`. Fix what they name; a re-run finishes what is left and does "
                    "not repeat what landed.", ["apply"], approve=True)
    if len(halves) == 1:
        other = "pipeline" if halves == ["capture"] else "capture"
        pending.append({"item": "half-applied", "detail": f"the {other} half has not run"})
        if not (other == "pipeline" and capture_only):
            return step(cli("apply", out_dir, f"--{other}-only"), f"Only the {halves[0]} half "
                        "was applied; the migration is half-applied until this runs.",
                        ["apply"], approve=True)
    if verified is None or _stamp(verified) < _stamp(applied):
        return step(cli("verify", out_dir, "--notebook"), "Applied, and not verified since.",
                    ["verify"])
    if any(app.get("status") == "failed" for app in verified.get("applications") or []):
        return step(cli("verify", out_dir, "--notebook"), "verify.json reports failed checks; "
                    "each names what it compared. Fix the cause, then verify again.", ["verify"])
    return step(None, "Applied and verified. What is left is the hand-off: code-changes.json, "
                "and the queries once traffic has arrived.", ["handoff", "verify"])


def command_status(args: argparse.Namespace) -> int:
    """Where an out-dir stands, and the one command that comes next. Reads local files only."""
    if not str(args.out_dir).strip():
        raise UsageError("--out-dir is empty. Name the directory the artifacts are in.",
                         fix=FIX_OUT_DIR)
    out_dir = Path(args.out_dir)
    found = {name: read_local(out_dir / name) for name in STATUS_ARTIFACTS}
    # Markdown, so it has no stamp of its own: it counts if it was written after the plan.
    report_path, plan_path = out_dir / REPORT_FILENAME, out_dir / "plan.json"
    found[REPORT_FILENAME] = (
        {"path": str(report_path)}
        if report_path.exists() and plan_path.exists()
        and report_path.stat().st_mtime >= plan_path.stat().st_mtime
        else None
    )
    phases = {
        name[: -len(".json")]: {"at": _stamp(artifact) or None, "tenant": _tenant_of(artifact)}
        for name, artifact in found.items()
        if artifact is not None and name not in ("openpipeline-payload.json", REPORT_FILENAME)
    }
    tenants = sorted({phase["tenant"] for phase in phases.values() if phase["tenant"]})
    if len(tenants) > 1:
        nxt = {
            "nextCommand": None,
            "nextStep": f"This --out-dir holds artifacts from {len(tenants)} tenants "
            f"({', '.join(tenants)}). Use one --out-dir per tenant and start the other over "
            "with `preflight`.",
            "read": ["prerequisites"], "approve": None, "pending": [],
        }
    else:
        nxt = status_next(found, str(args.out_dir))
    summary: Dict[str, Any] = {
        "command": "status",
        "outDir": str(out_dir.resolve()),
        "tenant": tenants[0] if len(tenants) == 1 else (tenants or None),
        "phases": phases,
        "pending": nxt["pending"],
        "nextCommand": nxt["nextCommand"],
        "nextStep": nxt["nextStep"],
        "status": "ok",
    }
    guide(summary, read=nxt["read"], approve=nxt["approve"])
    print(json.dumps(summary, indent=2))
    return EXIT_OK


# --------------------------------------------------------------------------- cli


def command_scan(args: argparse.Namespace) -> int:
    only_ids = args.application or None
    if only_ids and args.all:
        raise UsageError(
            "--application and --all are mutually exclusive: name the applications to read, or "
            "ask for all of them.",
            fix=["Drop --all to read only the named applications, or drop --application to read "
                 "them all."],
        )

    if not str(args.out_dir).strip():
        raise UsageError(
            "--out-dir is empty. It is usually an unset shell variable; name the directory "
            "explicitly rather than writing the tenant's configuration into the working directory.",
            fix=FIX_OUT_DIR,
        )

    settings = load_settings(config_path=Path(args.config) if args.config else None)
    client = classic_client(settings, timeout=args.timeout)
    kinds: Tuple[str, ...] = tuple(args.kinds)
    progress = None if args.quiet else progress_to_stderr
    host = classic_host(settings)
    only_ids, resolved = resolve_applications(client, only_ids, kinds)

    auto_read: Optional[List[str]] = None
    if not only_ids and not args.all:
        inventory = run_inventory(client, kinds=kinds, progress=progress)
        inventory_path = write_artifact(
            Path(args.out_dir), "inventory.json", inventory_artifact(inventory, classic_host=host)
        )
        # A handful of applications is read outright: asking which of four to read, when
        # finding out costs four seconds, is a question not worth asking. Above the threshold
        # the count is reported and the choice is yours -- a sweep is one request per
        # application, and you are the one who waits for it.
        if inventory.entries and len(inventory.entries) <= args.max_auto_read:
            auto_read = [entry["id"] for entry in inventory.entries]
            if progress is not None:
                progress(
                    f"{len(auto_read)} applications is few enough to read outright; reading them"
                )
        else:
            artifact = inventory_artifact(inventory, classic_host=host)
            summary = summarise_inventory(artifact)
            summary["artifact"] = str(inventory_path)
            summary["tenant"] = host
            summary["status"] = (
                "failed" if inventory.errors and not inventory.entries
                else "partial" if inventory.errors
                else "ok"
            )
            inventory_guide(summary)
            print(json.dumps(summary, indent=2))
            if summary["status"] == "failed":
                return EXIT_API
            return EXIT_PARTIAL if inventory.errors else EXIT_OK

    result = run_scan(
        client,
        kinds=kinds,
        only_ids=only_ids or auto_read,
        all_applications=bool(args.all),
        progress=progress,
    )
    artifact = scan_artifact(
        result,
        classic_host=host,
        mode="all" if args.all else "auto" if auto_read is not None else "selected",
    )
    path = write_artifact(Path(args.out_dir), "scan.json", artifact)

    summary = summarise_scan(artifact)
    summary["artifact"] = str(path)
    summary["tenant"] = host
    listing_failed = any(e["stage"] == "list" for e in result.errors)
    summary["status"] = (
        "failed" if listing_failed and not result.applications
        else "partial" if result.errors
        else "ok"
    )
    if resolved:
        summary["resolvedNames"] = resolved
    scan_guide(summary, args.out_dir)
    print(json.dumps(summary, indent=2))

    if summary["status"] == "failed":
        return EXIT_API
    return EXIT_PARTIAL if result.errors else EXIT_OK


ROW2_CHOICES = ("A", "B", "C")
ROW2_DEFAULT = "C"


def parse_row2_overrides(raw: Optional[List[str]]) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    for item in raw or []:
        key, separator, option = item.rpartition("=")
        if not separator or not key:
            raise UsageError(
                f"--row2-key expects `<classic key>=A|B|C`, got {item!r}. The key is the classic "
                "property key, as it appears in scan.json.",
                fix=["Pass --row2-key KEY=A, KEY=B or KEY=C, KEY being the classic property key as "
                     "scan.json lists it."],
            )
        option = option.strip().upper()
        if option not in ROW2_CHOICES:
            raise UsageError(
                f"--row2-key {key}= expects one of A, B or C, got {option!r}.",
                fix=["Pass --row2-key KEY=A, KEY=B or KEY=C, KEY being the classic property key as "
                     "scan.json lists it."],
            )
        overrides[key] = option
    return overrides


# The two spellings each answer accepts. Written out rather than coerced, so a typo is a usage
# error naming the key rather than a silent `false`.
DROP_SOURCE_TRUE = ("yes", "y", "true", "1", "drop")
DROP_SOURCE_FALSE = ("no", "n", "false", "0", "keep")


def parse_drop_source_overrides(raw: Optional[List[str]]) -> Dict[str, bool]:
    """`--drop-event-property-key <key>=yes|no`, one key at a time.

    The key is the **classic** property key for a property and the generated
    `user_tag_<uniqueId>` key for a user tag, which is the only name a classic tag has on this
    side of the migration.
    """
    overrides: Dict[str, bool] = {}
    for item in raw or []:
        key, separator, answer = item.rpartition("=")
        if not separator or not key:
            raise UsageError(
                f"--drop-event-property-key expects `<key>=yes|no`, got {item!r}. The key is "
                "the classic property key as it appears in scan.json, or the generated "
                "`user_tag_<uniqueId>` key for a user tag.",
                fix=["Pass --drop-event-property-key KEY=yes or KEY=no, KEY being the classic property "
                     "key as scan.json lists it, or `user_tag_<uniqueId>` for a user tag."],
            )
        answer = answer.strip().lower()
        if answer in DROP_SOURCE_TRUE:
            overrides[key] = True
        elif answer in DROP_SOURCE_FALSE:
            overrides[key] = False
        else:
            raise UsageError(
                f"--drop-event-property-key {key}= expects yes or no, got {answer!r}.",
                fix=["Pass --drop-event-property-key KEY=yes or KEY=no, KEY being the classic property "
                     "key as scan.json lists it, or `user_tag_<uniqueId>` for a user tag."],
            )
    return overrides


def parse_expression_overrides(raw: Optional[List[str]]) -> Dict[str, str]:
    """`--expression <key>=<DQL>`. Split on the **first** `=`, because DQL has `==` and a key
    has no `=`."""
    fix = ["Pass --expression KEY=<DQL>, KEY being the classic property key as scan.json lists "
           "it, or `user_tag_<uniqueId>` for a user tag, and quote the whole argument for the "
           "shell."]
    overrides: Dict[str, str] = {}
    for item in raw or []:
        key, separator, expression = item.partition("=")
        key, expression = key.strip(), expression.strip()
        if not separator or not key:
            raise UsageError(f"--expression expects `<key>=<DQL expression>`, got {item!r}.", fix=fix)
        if not expression:
            raise UsageError(f"--expression {key}= carries no expression.", fix=fix)
        if CLEANUP_PLACEHOLDER_PREFIX in expression:
            raise UsageError(
                f"--expression {key}= still carries the placeholder; it has to be the "
                "expression that replaces it.",
                fix=fix,
            )
        if key in overrides:
            raise UsageError(f"--expression names {key!r} twice.", fix=["Pass each key once."])
        overrides[key] = expression
    return overrides


def load_scan_artifact(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise UsageError(
            f"no scan artifact at {path}. Run `scan` first, or point --scan at the scan.json it "
            "wrote -- `plan` reads that file and never the tenant.",
            fix=["Run `scan` with this --out-dir, or pass --scan PATH naming the scan.json it wrote."],
        )
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(
            f"{path} could not be read as JSON: {exc}",
            fix=["Re-run the command that wrote it, or pass the flag naming a copy this tool "
                 "wrote, unedited."],
        ) from exc
    if not isinstance(artifact, dict) or artifact.get("artifact") != "scan":
        raise UsageError(
            f"{path} is not a scan artifact -- it carries "
            f"{artifact.get('artifact')!r} rather than 'scan'.",
            fix=["Run `scan` with this --out-dir, or pass --scan PATH naming the scan.json it wrote."],
        )
    return artifact


def command_plan(args: argparse.Namespace) -> int:
    """`plan` never touches the tenant: it reads a scan artifact and writes local files.

    That is not a limitation. The merge against the existing settings object, and the backup of
    it, belong to `apply`, which re-reads immediately before writing -- a merge computed here
    would be computed against a read that may be days stale by the time it is applied.
    """
    if not str(args.out_dir).strip():
        raise UsageError(
            "--out-dir is empty. It is usually an unset shell variable; name the directory "
            "explicitly rather than writing the tenant's configuration into the working directory.",
            fix=FIX_OUT_DIR,
        )
    out_dir = Path(args.out_dir)
    scan_path = Path(args.scan) if args.scan else out_dir / "scan.json"
    scan = load_scan_artifact(scan_path)

    plan = plan_artifact(
        scan,
        # C unless told otherwise: session scope kept, without code. The plan says so, and says
        # that it means pipeline changes, so a user who does not want them can pick A or B.
        row2_default=args.row2 or ROW2_DEFAULT,
        row2_defaulted=args.row2 is None,
        row2_overrides=parse_row2_overrides(args.row2_key),
        drop_source_default=bool(getattr(args, "drop_event_property", False)),
        drop_source_overrides=parse_drop_source_overrides(
            getattr(args, "drop_event_property_key", None)
        ),
        scan_path=str(scan_path.resolve()),
        pipeline_id=args.pipeline_id,
        expressions=parse_expression_overrides(getattr(args, "expression", None)),
    )
    written = {"plan.json": write_artifact(out_dir, "plan.json", plan)}
    derived = derived_artifacts(plan)
    for name, payload in derived.items():
        written[name] = write_artifact(out_dir, name, payload)

    summary = summarise_plan(plan)
    # `plan` talks to no tenant; this is the one the scan was taken on.
    summary["tenant"] = (scan.get("environment") or {}).get("classicHost")
    summary["artifacts"] = {name: str(path) for name, path in written.items()}
    summary["status"] = "decisions-pending" if summary["decisionsPending"] else "ok"
    plan_guide(summary, derived["openpipeline-payload.json"], args.out_dir)
    print(json.dumps(summary, indent=2))
    return EXIT_OK


def load_plan_artifact(path: Path, *, phase: str = "apply") -> Dict[str, Any]:
    if not path.exists():
        # Name the phase that is asking. The likeliest cause is an --out-dir that is not the one
        # `plan` wrote to, and a message that names the wrong phase sends you looking in the
        # wrong place.
        verb = {"verify": "verifies", "report": "renders"}.get(phase, "writes") + " what `plan` planned"
        raise UsageError(
            f"no plan artifact at {path}. Run `plan` first, or point --plan at the plan.json it "
            f"wrote -- `{phase}` {verb} and nothing it derives itself. If `plan` did run, check "
            "that --out-dir is the directory it wrote to.",
            fix=["Run `plan` with this --out-dir, or pass --plan PATH naming the plan.json it wrote."],
        )
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(
            f"{path} could not be read as JSON: {exc}",
            fix=["Re-run the command that wrote it, or pass the flag naming a copy this tool "
                 "wrote, unedited."],
        ) from exc
    if not isinstance(artifact, dict) or artifact.get("artifact") != "plan":
        raise UsageError(
            f"{path} is not a plan artifact -- it carries "
            f"{artifact.get('artifact')!r} rather than 'plan'.",
            fix=["Run `plan` with this --out-dir, or pass --plan PATH naming the plan.json it wrote."],
        )
    return artifact


def apply_halves(args: argparse.Namespace) -> Tuple[str, ...]:
    if args.capture_only:
        return ("capture",)
    if args.pipeline_only:
        return ("pipeline",)
    return ("capture", "pipeline")


def pipeline_to_apply(
    settings: Dict[str, str],
    plan: Dict[str, Any],
    args: argparse.Namespace,
    *,
    host: str,
    progress: Optional[Callable[[str], None]],
) -> Optional[PipelineRecord]:
    """The pipeline half, read and decided -- or None when this run has no pipeline half.

    Everything that refuses the half refuses it here, before the capture half has read anything,
    so a run that cannot finish both halves stops before it starts either.
    """
    if args.capture_only:
        return None
    payload = openpipeline_payload(plan)
    if not payload["processorCount"] and not payload["needsYourExpression"]:
        return None
    if args.application:
        raise UsageError(
            "--application narrows the capture half only. The pipeline and its route serve "
            "every application in the plan, and writing them for a subset would drop the "
            "others' routes. Add --capture-only, or leave --application out.",
            fix=[
                "Add --capture-only to write only the named applications' capture settings.",
                "Or leave --application out to write both halves for every planned application.",
            ],
        )
    if payload["problems"]:
        raise UsageError(
            f"the pipeline payload has {len(payload['problems'])} problem(s), listed in "
            "openpipeline-payload.json under `problems`: "
            + "; ".join(str(problem) for problem in payload["problems"][:5])
            + ". The tenant would refuse it, or take a placeholder as a value. Nothing was "
            "written.",
            fix=[
                "Write the capture settings with `apply --capture-only`, then create the pipeline "
                "and its route by hand from openpipeline-payload.json (`create`, `route`), with "
                "each problem it names corrected.",
                "If a problem is caused by a `plan` option (`plan --help`), change that option, "
                "re-run `plan`, then `apply`.",
            ],
        )
    if payload["needsYourExpression"]:
        keys = ", ".join(
            f"{entry.get('applicationId')}:{entry.get('key')}"
            for entry in payload["needsYourExpression"]
        )
        raise UsageError(
            f"{len(payload['needsYourExpression'])} classic cleanup rule(s) have no exact "
            f"translation ({keys}; openpipeline-payload.json, `needsYourExpression`, says why "
            "and what each one has to extract). A pipeline without them migrates those values "
            "wrongly rather than not at all. Nothing was written.",
            fix=[
                "Write each DQL expression and re-run `plan` with --expression KEY=<expression> "
                "per entry (the entry's `supplyWith`), then `apply` again.",
                "Or write the capture settings alone with `apply --capture-only`.",
            ],
        )
    client, platform_host = platform_client(settings, timeout=args.timeout)
    refuse_other_platform(platform_host, host=host)
    record = PipelineRecord(payload, host=platform_host)
    record.client = client
    read_pipeline_state(client, record, progress=progress)
    return record


def command_apply(args: argparse.Namespace) -> int:
    """The first phase that writes to a tenant. Read everything, back it up, then write.

    There is no confirmation prompt, and that is deliberate: the human gate lives between `plan`
    and `apply`, where the plan artifacts are what the human is shown. A prompt here would be a
    second gate in the wrong place -- after the decision has already been taken, and in a script
    that is often run non-interactively.
    """
    if not str(args.out_dir).strip():
        raise UsageError(
            "--out-dir is empty. It is usually an unset shell variable; name the directory "
            "explicitly rather than writing the tenant's configuration into the working directory.",
            fix=FIX_OUT_DIR,
        )
    out_dir = Path(args.out_dir)
    plan_path = Path(args.plan) if args.plan else out_dir / "plan.json"
    plan = load_plan_artifact(plan_path)

    settings = load_settings(config_path=Path(args.config) if args.config else None)
    client, token_source = settings_client(settings, timeout=args.timeout, phase="apply")
    progress = None if args.quiet else progress_to_stderr
    host = classic_host(settings)
    refuse_other_tenant((plan.get("source") or {}).get("environment"), plan_path, host=host)

    if args.capture_only and args.pipeline_only:
        raise UsageError(
            "--capture-only and --pipeline-only together write nothing. Pick one.",
            fix=["Keep one of the two flags, or drop both to run both halves."],
        )
    pipeline = pipeline_to_apply(settings, plan, args, host=host, progress=progress)

    records: List[ApplyRecord] = []
    errors: List[Dict[str, Any]] = []
    if not args.pipeline_only:
        records, errors = read_current_objects(
            client, plan, only_ids=args.application or None, progress=progress
        )
        merge_changes(records, overwrite=args.overwrite_existing)
    pending = [record.id for record in records if record.action == "pending"]
    to_check = list(pending)
    if pipeline is not None and pipeline.pending():
        to_check += [app_id for app_id in pipeline.applications if app_id not in to_check]
    if not args.dry_run and to_check:
        # After the reads, so that a run with nothing to write needs no preflight; before the
        # backup, so that a refused run leaves nothing behind.
        require_preflight(out_dir, host=host, app_ids=to_check)

    backup_path: Optional[Path] = None
    if not args.dry_run and to_check:
        # Timestamped, and never overwritten. A second `apply` run reads a tenant this tool has
        # already changed, so a `backup.json` rewritten in place would replace the only record of
        # the original configuration with a record of the migrated one. `pending` is read after
        # the merge, so a run that changes nothing writes no backup at all.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = write_artifact(
            out_dir,
            f"backup-{stamp}.json",
            backup_artifact(
                records, classic_host=host, plan_path=str(plan_path.resolve()), pipeline=pipeline
            ),
        )

    errors.extend(
        write_changes(client, records, dry_run=args.dry_run, progress=progress)
    )
    if pipeline is not None:
        errors.extend(
            write_pipeline(
                pipeline.client, pipeline, dry_run=args.dry_run, progress=progress
            )
        )

    artifact = apply_artifact(
        records,
        plan=plan,
        classic_host=host,
        dry_run=args.dry_run,
        overwrite=args.overwrite_existing,
        plan_path=str(plan_path.resolve()),
        backup_path=str(backup_path) if backup_path else None,
        pipeline=pipeline,
        halves=apply_halves(args),
    )
    name = "apply-dry-run.json" if args.dry_run else "apply.json"
    path = write_artifact(out_dir, name, artifact)

    summary = summarise_apply(artifact)
    summary["tenant"] = host
    summary["tokenFrom"] = token_source
    summary["backup"] = str(backup_path) if backup_path else None
    summary["artifact"] = str(path)
    written = sum(
        summary["applicationsByAction"].get(action, 0) for action in ("created", "updated")
    )
    if pipeline is not None:
        written += sum(
            1
            for action in (pipeline.pipeline_action, pipeline.routing_action)
            if action in ("created", "updated")
        )
    summary["status"] = (
        "failed" if errors and not written
        else "partial" if errors or summary["problems"]
        else "ok"
    )
    apply_guide(summary, args)
    print(json.dumps(summary, indent=2))

    if summary["status"] == "failed":
        return EXIT_API
    return EXIT_PARTIAL if summary["status"] == "partial" else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Migrate classic RUM user-action and session properties to Grail.",
        epilog=scopes_epilogue(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"{TOOL_NAME} {TOOL_VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_out_dir(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--out-dir",
            default=DEFAULT_OUT_DIR,
            help="directory for artifacts (default: %(default)s)",
        )

    def add_common(sub: argparse.ArgumentParser) -> None:
        """Options for a phase that talks to a tenant. `plan` takes none of them, deliberately:
        offering `--config` on a phase that needs no credentials suggests it needs credentials."""
        entry = PHASE_SCOPES.get(sub.prog.split()[-1])
        if entry:
            sub.epilog = "scopes: " + entry["summary"] + "\n\n" + entry["note"]
            sub.formatter_class = argparse.RawDescriptionHelpFormatter
        add_out_dir(sub)
        sub.add_argument(
            "--config",
            default=None,
            help=f"path to a {CONFIG_FILE_NAME} file (default: {CONFIG_FILE_NAME} in the "
            "working directory). The file is parsed by this tool and never printed.",
        )
        sub.add_argument(
            "--quiet",
            action="store_true",
            help="suppress the progress lines on stderr (stdout is unaffected)",
        )
        sub.add_argument(
            "--timeout",
            type=float,
            default=DEFAULT_TIMEOUT,
            help="per-request timeout in seconds (default: %(default)s)",
        )

    preflight = subparsers.add_parser(
        "preflight",
        help="check the tenant, the credentials and the gates; writes nothing to the tenant",
        description="Step 1. Names the tenant this tool talks to, where each setting came from, "
        "and checks the capture schema, settings.write (validate-only), the platform token, and "
        "per application: readable, New RUM enabled, RUM JavaScript version. `apply` refuses to "
        f"write without a {PREFLIGHT_FILENAME} from the last {PREFLIGHT_MAX_AGE_HOURS} hours "
        "that covers the applications it writes.",
    )
    add_common(preflight)
    preflight.add_argument(
        "--application",
        action="append",
        metavar="ID_OR_NAME",
        help="check this application too: its entity id, or its exact name when only one "
        "application carries it; repeatable",
    )
    preflight.set_defaults(func=command_preflight)

    scan = subparsers.add_parser(
        "scan",
        help="list classic applications, or read the ones named; writes nothing to the tenant",
    )
    add_common(scan)
    scan.add_argument(
        "--application",
        action="append",
        metavar="ID_OR_NAME",
        help="read this application: its entity id, or its exact name when only one application "
        "carries it; repeatable. The enumeration is skipped for ids, so this costs one "
        "request per application named. Without it, and without --all, scan only lists what is "
        "there.",
    )
    scan.add_argument(
        "--max-auto-read",
        type=int,
        default=MAX_AUTO_READ,
        metavar="N",
        help="if the tenant has no more than N applications, read them all instead of just "
        "listing them (default: %(default)s). 0 always stops at the listing.",
    )
    scan.add_argument(
        "--all",
        action="store_true",
        help="read every application on the tenant. One request each, so a tenant with hundreds "
        "of applications takes minutes; prefer --application.",
    )
    scan.add_argument(
        "--web-only",
        dest="kinds",
        action="store_const",
        const=("web",),
        default=("web", "mobile"),
        help="list or read classic web applications only (default: both). Ignored when "
        "--application is given: the entity id says which kind it is.",
    )
    scan.add_argument(
        "--mobile-only",
        dest="kinds",
        action="store_const",
        const=("mobile",),
        help="list or read classic mobile applications only",
    )
    scan.set_defaults(func=command_scan)

    plan = subparsers.add_parser(
        "plan",
        help="classify, translate and validate; reads a scan artifact, writes local files only",
        description="Reads a scan artifact and writes local files. This phase never contacts a "
        "tenant, so it needs no credentials.",
    )
    add_out_dir(plan)
    plan.add_argument(
        "--scan",
        default=None,
        help="path to the scan artifact to plan from (default: scan.json in --out-dir)",
    )
    plan.add_argument(
        "--row2",
        choices=ROW2_CHOICES,
        default=None,
        help="the disposition for decision-table row 2 -- META_DATA properties that are "
        "session-scoped. A: accept event scope. B: keep session scope with a code change. "
        "C (the default): keep session scope with an OpenPipeline promotion rule, which means a "
        "pipeline and a route that `apply` writes. Pass A or B when pipeline changes are not "
        "wanted.",
    )
    plan.add_argument(
        "--row2-key",
        action="append",
        metavar="KEY=OPTION",
        help="the row-2 disposition for one classic key, overriding --row2; repeatable",
    )
    plan.add_argument(
        "--drop-event-property",
        action="store_true",
        help="remove the carrier `event_properties.<key>` in the pipeline once it has been "
        "read -- after a row-2C promotion has copied it onto the session, and after a user "
        "tag has been lifted into user.identifier. Classic gave each of those values one "
        "scope and it was not the event; the carrier exists because configuration-driven "
        "capture cannot write anything else. Off by default: it is one more processor per "
        "key, it saves nothing, and anything still reading the event property stops seeing "
        "it. The capture-properties entry is never removed -- the value still has to be "
        "captured before it can be promoted or lifted.",
    )
    plan.add_argument(
        "--drop-event-property-key",
        action="append",
        metavar="KEY=yes|no",
        help="the carrier disposition for one key, overriding --drop-event-property; "
        "repeatable. The key is the classic property key, or the generated "
        "`user_tag_<uniqueId>` key for a user tag",
    )
    plan.add_argument(
        "--expression",
        action="append",
        metavar="KEY=DQL",
        help="the DQL expression that replaces one classic cleanup rule; repeatable. Needed "
        "only where the rule has no exact translation (`needsYourExpression`), and used as "
        "given wherever it is passed. The key is the classic property key, or the generated "
        "`user_tag_<uniqueId>` key for a user tag; everything after the first `=` is the "
        "expression",
    )
    plan.add_argument(
        "--pipeline-id",
        default=None,
        metavar="CUSTOM_ID",
        help="append the pipeline processors to this existing custom pipeline (its customId) "
        "and leave routing alone, instead of creating the `rum_property_migration` pipeline "
        "and a route to it. Not recommended: the processors then run only on what that "
        "pipeline's routes already send it, and the pipeline is someone else's object. Built-in "
        "and default pipelines cannot be edited.",
    )
    plan.set_defaults(func=command_plan)

    apply_cmd = subparsers.add_parser(
        "apply",
        help="write the merged capture-properties objects",
        description="Reads a plan artifact, re-reads the settings objects it targets, backs "
        "them up, merges the planned entries into them and writes. This is the first phase "
        "that changes a tenant.",
    )
    add_common(apply_cmd)
    apply_cmd.add_argument(
        "--plan",
        default=None,
        help="path to the plan artifact to apply (default: plan.json in --out-dir)",
    )
    apply_cmd.add_argument(
        "--application",
        action="append",
        metavar="ENTITY_ID",
        help="apply only this application; repeatable. It has to be one the plan covers.",
    )
    apply_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="read and merge, write nothing to the tenant, and record what would have been "
        "written in apply-dry-run.json. No backup file is written: nothing changed, so there "
        "is nothing to restore.",
    )
    apply_cmd.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="replace a Gen3 property the tenant already has when the planned definition "
        "differs. Without it the existing definition is kept and both are reported: the "
        "existing one may have been configured deliberately.",
    )
    apply_cmd.add_argument(
        "--capture-only",
        action="store_true",
        help="write the capture settings and not the pipeline or its route. The migration is "
        "half-applied until --pipeline-only has run against the same plan.",
    )
    apply_cmd.add_argument(
        "--pipeline-only",
        action="store_true",
        help="write the pipeline and its route and not the capture settings. The migration is "
        "half-applied until --capture-only has run against the same plan.",
    )
    apply_cmd.set_defaults(func=command_apply)

    verify = subparsers.add_parser(
        "verify",
        help="read back what was written, and emit the checks that need traffic",
        description="Reads the settings objects back and checks them against the plan and the "
        "backup. Writes nothing to the tenant.",
    )
    add_common(verify)
    verify.add_argument(
        "--plan",
        default=None,
        help="path to the plan artifact that was applied (default: plan.json in --out-dir)",
    )
    verify.add_argument(
        "--backup",
        default=None,
        help="path to the backup the applying run wrote (default: the newest backup-<stamp>.json "
        "in --out-dir). It is what proves the merge kept what was already there, so without it "
        "that check is reported as skipped rather than passed.",
    )
    verify.add_argument(
        "--no-backup",
        action="store_true",
        help="verify without a backup, accepting that the merge cannot be checked",
    )
    verify.add_argument(
        "--application",
        action="append",
        metavar="ENTITY_ID",
        help="verify only this application; repeatable. It has to be one the plan covers.",
    )
    verify.add_argument(
        "--notebook",
        nargs="?",
        const="",
        default=None,
        metavar="NAME",
        help="also write a results notebook you can import, naming the file NAME (default: "
        f"{NOTEBOOK_FILENAME} in --out-dir). It reports what was migrated, what was skipped and "
        "what could not be migrated, and carries the queries that show whether the migrated "
        "properties are arriving. The queries are not run here -- they need traffic, and the "
        "notebook runs them when you open it. Uploading the file by hand titles the notebook "
        "after the file; applying it through an API or a command line uses the title inside it.",
    )
    verify.add_argument(
        "--apply",
        default=None,
        help="path to the applying run the notebook reports on (default: apply.json in "
        "--out-dir). Only read when --notebook is given.",
    )
    verify.set_defaults(func=command_verify)

    restore = subparsers.add_parser(
        "restore",
        help="write a backup artifact back",
        description="Reads a backup artifact, re-reads the settings objects it covers, "
        "snapshots them, and writes the backed-up state back -- deleting the objects the "
        "backed-up run created. This phase changes a tenant.",
    )
    add_common(restore)
    restore.add_argument(
        "--backup",
        default=None,
        help="path to the backup to write back (default: the newest backup-<stamp>.json in "
        "--out-dir). The newest is the one the last run that changed anything wrote.",
    )
    restore.add_argument(
        "--application",
        action="append",
        metavar="ENTITY_ID",
        help="restore only this application; repeatable. It has to be one the backup covers.",
    )
    restore.add_argument(
        "--dry-run",
        action="store_true",
        help="read and decide, write nothing to the tenant, and record what would have been "
        "written in restore-dry-run.json",
    )
    restore.add_argument(
        "--capture-only",
        action="store_true",
        help="restore the capture settings and leave the backup's pipeline section alone",
    )
    restore.add_argument(
        "--pipeline-only",
        action="store_true",
        help="undo the backup's pipeline section -- the route first, then the pipeline -- and "
        "leave the capture settings alone",
    )
    restore.set_defaults(func=command_restore)

    status = subparsers.add_parser(
        "status",
        help="where an out-dir stands, and the one command that comes next; reads local files only",
        description="Reads the artifacts in --out-dir and reports which phases ran, against which "
        "tenant, what is still pending, and the one command to run next. It talks to no tenant, "
        "so it needs no credentials. Run it when resuming, or when unsure what comes next.",
    )
    add_out_dir(status)
    status.set_defaults(func=command_status)

    report = subparsers.add_parser(
        "report",
        help="render the plan as plan-report.md, the page the user decides on; reads local files only",
        description="Writes plan-report.md into --out-dir from plan.json: the properties per "
        "application, the row-2 choices, the user tags in the order they are tried, what cannot "
        "migrate and which layer blocks it, cost, the pipeline and what is still open, and the "
        "apply command a yes leads to. Present it as written. It talks to no tenant.",
    )
    add_out_dir(report)
    report.add_argument(
        "--plan",
        default=None,
        help="path to the plan artifact to render (default: plan.json in --out-dir)",
    )
    report.set_defaults(func=command_report)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except MigratorError as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": redact(str(exc)),
                    "whatToDo": [redact(step) for step in exc.what_to_do],
                },
                indent=2,
            )
        )
        return exc.exit_code
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
