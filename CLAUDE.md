# Dynatrace Plugin

This plugin includes skills as well as the Dynatrace MCP server for Dynatrace platform access.

## Required setup for Dynatrace MCP Server

Set these environment variables, e.g., in `~/.claude/settings.json` under `env`:

- `DT_ENVIRONMENT` — your Dynatrace environment URL, e.g. `https://abc12345.apps.dynatrace.com` (Note: `https://` is required)
- `DT_PLATFORM_TOKEN` — a platform token with at least MCP gateway scopes

Consult the [Dynatrace MCP server docs
](https://docs.dynatrace.com/docs/shortlink/dynatrace-mcp-server) for a full list of scopes required for using the MCP Server with a Platform Token.

## Skills for Observability related questions

Please use the included skills for observability related questions.

## Version consistency

The canonical version lives in `.claude-plugin/plugin.json` (`version` field). It must match the latest GitHub release tag (e.g., release `v7.0.0` → version `7.0.0`).

When bumping that version, update all of the following to match:
- `.cursor-plugin/plugin.json` → `"version"`
- `mcp.json` → `"X-Http-Source": "dynatrace-for-ai/<version>"`
- `.mcp.json` → `"X-Http-Source": "dynatrace-for-ai/<version>"`

The CI workflow `.github/workflows/check-versions.yml` enforces this and will fail if they drift.