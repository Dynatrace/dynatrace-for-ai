# Genuine false positives only, one line each with the reason.
# Not type-checked or linted: vulture parses this file, it is never executed.
# pylint: skip-file
# pyright: ignore

# pytest collects autouse fixtures by decoration, so no call site references them by name.
_tokened_env  # type: ignore[name-defined]  # noqa: F821
