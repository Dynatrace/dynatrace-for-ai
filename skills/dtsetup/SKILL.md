---
name: dtsetup
description: >
  First-time setup of the Dynatrace MCP server `plugin:dynatrace:mcp`.
  Run this when the user wants to connect to Dynatrace or when Dynatrace MCP
  tools are not in your available tool list. Relevant when the user wants to
  query metrics, logs, traces, problems, dashboards, or any other Dynatrace
  data.
---

## Dynatrace MCP Server

The Dynatrace MCP server is `plugin:dynatrace:mcp`. Always use this specific
server — do not substitute another.

**If `plugin:dynatrace:mcp` tools are not in your available tools, run this
skill first.** Missing tools mean the server needs setup or is disconnected —
they are not evidence that Dynatrace is unavailable.

## Shared reference

Read [references/mcp-settings.md](references/mcp-settings.md) before
proceeding. It contains the `dynatrace-server-state` check, the registration
file location, and the editing rules used in the steps below.

---

## Entry flow

Check `dynatrace-server-state` (see `mcp-settings.md`):

- **working** — tell the user the server is already connected with the current
  environment ID. Ask if they want to reconfigure. If no, stop.
- **not-setup** — proceed to the [Setup procedure](#setup-procedure) below.
- **not-working** — tell the user the server is configured but not responding,
  suggest they check that `DT_ENVIRONMENT_ID` and `DT_PLATFORM_TOKEN` are set
  correctly (or re-run `/dtsetup` to reconfigure), and stop.

---

## Setup procedure

### Step 1 — Ask for the Dynatrace Environment ID

Tell the user you need their Dynatrace environment ID to connect. This is the
ID in their Dynatrace URL:

| URL | Environment ID |
|-----|----------------|
| `https://abc12345.apps.dynatrace.com` | `abc12345` |
| `https://xyz98765.live.dynatrace.com` | `xyz98765` |

If unsure, ask the user to open their Dynatrace environment in a browser and
copy the subdomain from the address bar.

### Step 2 — Ask for a Dynatrace Platform Token

Tell the user you also need a Dynatrace Platform Token with MCP access. If
they don't have one, guide them:

1. In Dynatrace, open **Settings** → **Access tokens** (older environments:
   **Identity & access management** → **Access tokens**)
2. Click **Generate new token**
3. Add the scopes required by the [Dynatrace MCP server](https://docs.dynatrace.com/docs/shortlink/dynatrace-mcp-server)
4. Copy the generated token

Do **not** show, echo, or log the token at any point.

### Step 3 — Apply the configuration

**3a. Edit the registration file.** Use the Edit tool to update
`<plugin-root>/.mcp.json` (see `mcp-settings.md` for the path and editing
rule). Replace `not-setup` with the environment ID provided:

Before:
```
"${DT_ENVIRONMENT_ID:-not-setup}"
```
After (example — use the actual environment ID, not `abc12345`):
```
"${DT_ENVIRONMENT_ID:-abc12345}"
```

**3b. Save the platform token.** Use the Bash tool to write the token to the
plugin data directory:

```bash
mkdir -p "${CLAUDE_PLUGIN_DATA}" && printf '%s' 'THE_TOKEN' > "${CLAUDE_PLUGIN_DATA}/dt-platform-token" && chmod 600 "${CLAUDE_PLUGIN_DATA}/dt-platform-token"
```

Substitute `THE_TOKEN` with the actual token value. Do not print the command
with the real token visible; use a sub-expression or write the value directly
without echoing it.

### Step 4 — Finish

Tell the user the Dynatrace MCP server has been configured. Instruct them to:

1. Run `/reload-plugins`
2. The server will connect automatically — no further authentication needed

Do not reveal the token, the file path, or any file contents.

---

## Advanced: environment variable overrides

If `DT_ENVIRONMENT_ID` or `DT_PLATFORM_TOKEN` are set as environment variables
before starting `claude`, they take precedence over the values stored by this
skill. Power users can use this instead of running `/dtsetup`.
