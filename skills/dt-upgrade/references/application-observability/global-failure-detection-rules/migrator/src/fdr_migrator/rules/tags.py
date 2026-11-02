from __future__ import annotations

from dataclasses import dataclass

# A tag entry is one string, not a `{context, key, value}` object: the serialised form of a
# universal tag, `[Context]key:value`, where the context prefix and `:value` are both optional
# and a literal colon inside either part is escaped as `\:`. Every key test below therefore runs
# on the *parsed* key - a prefix test against the raw entry misjudges the context-prefixed form.
_ESCAPED_COLON = "\\:"
PRIMARY_TAG_PREFIX = "primary_tags."

# Contexts are recognised by their prefix spelling or by their enum name, case-sensitively. An
# unrecognised prefix is not stripped: it stays part of the key, so `[BOGUS]primary_tags.env` is
# the key `[BOGUS]primary_tags.env` and is not a primary tag.
_KNOWN_CONTEXTS = frozenset(
    {
        # No prefix at all is the contextless form, which is the common case.
        "",
        "AWS",
        "AWSGeneric",
        "AWS_GENERIC",
        "Azure",
        "AZURE",
        "CloudFoundry",
        "CLOUD_FOUNDRY",
        "CONTEXTLESS",
        "Environment",
        "ENVIRONMENT",
        "GoogleCloud",
        "GOOGLE_COMPUTE_ENGINE",
        "Kubernetes",
        "KUBERNETES",
    }
)


@dataclass(frozen=True)
class ParsedTag:
    """A tag entry after parsing, with a *null* value kept distinct from an empty one.

    A tag-equals entry carrying no `:value` matches only tags whose value is null, which is
    strictly narrower than matching the key alone - so the two must never collapse into one.
    """

    key: str
    value: str | None


def parse_universal_tag(entry: str) -> ParsedTag | None:
    """Split a serialised tag entry into its key and value, or ``None`` if it has no key."""
    remainder = entry
    prefix = ""
    if entry.startswith("[") and "]" in entry:
        closing = entry.index("]")
        prefix = entry[1:closing].replace(_ESCAPED_COLON, ":")
        remainder = entry[closing + 1 :]

    parts = _split_on_unescaped_colon(remainder)
    if not parts:
        return None
    key = parts[0]
    if prefix not in _KNOWN_CONTEXTS:
        key = f"[{prefix}]{key}"
    value = ":".join(parts[1:])
    return ParsedTag(key, value or None)


def serialise_universal_tag(tag: ParsedTag) -> str:
    """Write a parsed tag back as the one string a predicate stores it as.

    A colon inside either part is escaped, since an unescaped one is what separates key from
    value: written plainly, a value of `a:b` would be stored as a value of `b` under a longer key.
    No context prefix is written - the contextless form is the one with nothing to strip, and a
    parsed key that needed one already carries it.
    """
    if tag.value is None:
        return _escaped(tag.key)
    return f"{_escaped(tag.key)}:{_escaped(tag.value)}"


def _escaped(part: str) -> str:
    return part.replace(":", _ESCAPED_COLON)


def is_primary_tag_key(key: str) -> bool:
    """A Primary Tag survives Phase 3; every other tag key stops being evaluated.

    Recognition needs a non-empty remainder after the prefix: `primary_tags.` on its own names no
    tag and is not primary.
    """
    trimmed = key.strip()
    return trimmed.startswith(PRIMARY_TAG_PREFIX) and len(trimmed) > len(PRIMARY_TAG_PREFIX)


def _split_on_unescaped_colon(text: str) -> list[str]:
    if ":" not in text:
        return [text]
    parts: list[str] = []
    current = ""
    for chunk in _dropped_trailing_blanks(text.split(":")):
        current += chunk
        if current.endswith("\\"):
            current = current[:-1] + ":"
            continue
        parts.append(current)
        current = ""
    if current:
        parts.append(current)
    return parts


def _dropped_trailing_blanks(chunks: list[str]) -> list[str]:
    # A trailing `:` adds no value part - `team-payments:` is the valueless `team-payments`.
    end = len(chunks)
    while end > 0 and chunks[end - 1] == "":
        end -= 1
    return chunks[:end]
