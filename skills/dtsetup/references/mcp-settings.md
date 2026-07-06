# Dynatrace MCP Registration Reference

Shared reference used by `dtsetup`. Contains the registration file location,
editing rules, and state-check procedure.

---

## Stay on script

Describe state and actions in plain language only. Never reveal to the user:

- File paths, file names, or directory layout
- The `not-setup` sentinel value or related terms ("placeholder", "default value")
- Variable names, shell syntax, or `${…:-…}` notation
- Token values, credentials, or file contents of any kind

Emit only what the current step instructs. Do not add tips or follow-up notes
from general knowledge — when the user needs to reload or take any other action,
the skill emits that instruction at the correct step.

---

## Determine `dynatrace-server-state`

Silently determine the state using only these steps:

1. Try a lightweight MCP call on `plugin:dynatrace:mcp` (list tools, or read
   any resource). Use `server: "plugin:dynatrace:mcp"` explicitly.
2. If the server returns real, non-empty Dynatrace-specific content →
   `dynatrace-server-state` is **working**.
3. If the call fails or returns empty/generic content, read the registration
   file (see below). Check its raw content for the literal string `not-setup`:
   - Contains `not-setup` → **not-setup**
   - Otherwise → **not-working**

Do not tell the user which state was determined or what was checked.

---

## Registration file

Path: `<plugin-root>/.mcp.json`

If `<plugin-root>` is not already known, derive it from this file's path by
removing `skills/dtsetup/references/mcp-settings.md` from the end.

The URL field contains:

```
"url": "https://${DT_ENVIRONMENT_ID:-<current-env-id>}.apps.dynatrace.com/..."
```

### Editing rule

Each variable has the form `${NAME:-default}`. When editing, replace **only the
default value** — the characters between `:-` and the closing `}`. The `${`,
variable name, `:-`, and `}` must always remain intact.

Example — replacing the environment ID:

```
${DT_ENVIRONMENT_ID:-not-setup}  →  ${DT_ENVIRONMENT_ID:-abc12345}
```

### The `not-setup` sentinel

A fresh installation has `not-setup` as the default:

```
${DT_ENVIRONMENT_ID:-not-setup}
```

This prevents the server from connecting until `/dtsetup` replaces it with a
real environment ID. Once replaced it never returns to `not-setup`.
