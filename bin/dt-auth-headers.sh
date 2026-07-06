#!/usr/bin/env bash
# Outputs Authorization headers for the Dynatrace MCP server.
# Called by Claude Code as a headersHelper at session start and on reconnect.
#
# Token resolution order:
#   1. DT_PLATFORM_TOKEN environment variable (set by the user before launching claude)
#   2. CLAUDE_PLUGIN_DATA/dt-platform-token file (written by /dynatrace:dtsetup)
#   3. Empty string — the MCP server will return 401 and Claude Code will surface the error

token="${DT_PLATFORM_TOKEN:-}"

if [ -z "$token" ]; then
  # CLAUDE_PLUGIN_DATA is not in the headersHelper environment; derive the conventional path
  data_file="${HOME}/.claude/plugin-data/dynatrace/dt-platform-token"
  if [ -f "$data_file" ]; then
    token="$(cat "$data_file")"
  fi
fi

printf '{"Authorization": "Bearer %s"}' "$token"
