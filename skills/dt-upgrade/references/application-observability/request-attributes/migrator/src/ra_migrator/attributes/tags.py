"""The `[Context]key:value` tag a scope stores, read the way the backend reads it.

Every test of a tag runs on the **parsed key**. Testing the stored string instead reports
`[Environment]primary_tags.team` as deprecated when the runtime treats it as surviving, and
that string is a shape tenants really hold.
"""

from __future__ import annotations

from dataclasses import dataclass

PRIMARY_TAG_PREFIX = "primary_tags."

# Every context the backend recognises, under both spellings it accepts: the prefix it
# serialises and the name of the enum constant. Both are matched exactly and case-sensitively,
# and anything else is not a context at all - it stays part of the key, which is what makes
# `[BOGUS]primary_tags.env` a deprecated condition while `[Environment]primary_tags.env` is not.
_CONTEXTS = {
    "AWS": "AWS",
    "Environment": "ENVIRONMENT",
    "CloudFoundry": "CLOUD_FOUNDRY",
    "Kubernetes": "KUBERNETES",
    "GoogleCloud": "GOOGLE_COMPUTE_ENGINE",
    "Azure": "AZURE",
    "AWSGeneric": "AWS_GENERIC",
}
_CONTEXTS.update({name: name for name in [*_CONTEXTS.values(), "CONTEXTLESS"]})

CONTEXTLESS = "CONTEXTLESS"


@dataclass(frozen=True)
class Tag:
    """A parsed tag: its context, its key, and its value if it carries one."""

    context: str
    key: str
    value: str | None


def parse_tag(stored: str | None) -> Tag | None:
    """The stored string as the backend parses it, or `None` where the backend yields nothing.

    Nothing is trimmed at any point, so a padded key stays padded and stops being a primary tag.
    """
    if stored is None:
        return None
    prefix, remainder = _split_prefix(stored)
    parts = _split_on_unescaped_colons(remainder)
    if not parts:
        # The backend yields nothing for a string that splits into no parts at all, and a
        # condition holding no tag is one Phase 3 forbids.
        return None
    key, value = parts[0], ":".join(parts[1:])
    context = _CONTEXTS.get(prefix, CONTEXTLESS if prefix == "" else None)
    if context is None:
        # An unrecognised prefix is not a context: the backend puts it back into the key, where
        # it stops the key from being a primary tag.
        context, key = CONTEXTLESS, f"[{prefix}]{key}"
    return Tag(context, key, value or None)


def _split_prefix(stored: str) -> tuple[str, str]:
    """The `[...]` prefix and what follows it, taken exactly where the backend takes them."""
    if not stored.startswith("[") or "]" not in stored:
        return "", stored
    closing = stored.index("]")
    return stored[1:closing].replace("\\:", ":"), stored[closing + 1 :]


def _split_on_unescaped_colons(text: str) -> list[str]:
    """Split on every colon not preceded by a backslash, as the backend's own splitter does.

    Faithful down to two details that decide keys: a string with no colon at all is one part
    whatever else it holds, and empty parts at the end are dropped - so `":"` splits into
    nothing and a key ending in an escaped colon keeps it.
    """
    if ":" not in text:
        return [text]
    chunks = text.split(":")
    while chunks and chunks[-1] == "":
        chunks.pop()
    parts: list[str] = []
    carried = ""
    for chunk in chunks:
        carried += chunk
        if carried.endswith("\\"):
            carried = carried[:-1] + ":"
        else:
            parts.append(carried)
            carried = ""
    if carried:
        parts.append(carried)
    return parts


def is_bare_prefix(tag: Tag | None) -> bool:
    """Whether the key is the primary tag prefix and nothing more.

    Surviving to the runtime and rejected by the API validator, which is the one key the two
    rules disagree on. It names no span field, so the data source captures nothing today.
    """
    return tag is not None and tag.key == PRIMARY_TAG_PREFIX


def is_primary(tag: Tag | None) -> bool:
    """The runtime's rule, which has no length check, and not the API validator's stricter one.

    A tag the backend could not parse is not one either: the runtime's type test fails on it and
    the condition counts as forbidden.
    """
    return tag is not None and tag.key.startswith(PRIMARY_TAG_PREFIX)
