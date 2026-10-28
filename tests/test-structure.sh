#!/usr/bin/env bash
set -euo pipefail
# Test: Validate structural consistency between skills/, plugin manifests, and marketplace.json.
#
# Checks:
#   1. Every skill dir has SKILL.md
#   2. .claude-plugin/plugin.json exists and has name "dynatrace"
#   3. .cursor-plugin/plugin.json exists and has name "dynatrace"
#   4. marketplace.json is valid, references the dynatrace plugin, source uses ./ prefix
#   5. .antigravity-plugin/plugin.json has name "dynatrace", the Marketplace fields, an existing logo,
#      and at most 3 suggestedPrompts
#   6. mcp_config.json uses serverUrl and declares every ${VAR} placeholder in "variables"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== test-structure.sh ==="

python3 -c "
import json, sys, pathlib

root = pathlib.Path('$ROOT_DIR')
errors = []

# --- Discover skills on disk ---
skills_dir = root / 'skills'
disk_skills = set()
for d in sorted(skills_dir.iterdir()):
    if d.is_dir() and d.name.startswith('dt-'):
        skill_md = d / 'SKILL.md'
        if skill_md.exists():
            disk_skills.add(d.name)
        else:
            errors.append(f'Skill dir {d.name}/ has no SKILL.md')

# --- Check .claude-plugin/plugin.json ---
claude_plugin_path = root / '.claude-plugin' / 'plugin.json'
if not claude_plugin_path.exists():
    errors.append('Missing .claude-plugin/plugin.json')
else:
    pj = json.loads(claude_plugin_path.read_text())
    if pj.get('name') != 'dynatrace':
        errors.append(f'.claude-plugin/plugin.json name is \"{pj.get(\"name\")}\" not \"dynatrace\"')

# --- Check .cursor-plugin/plugin.json ---
cursor_plugin_path = root / '.cursor-plugin' / 'plugin.json'
if not cursor_plugin_path.exists():
    errors.append('Missing .cursor-plugin/plugin.json')
else:
    pj = json.loads(cursor_plugin_path.read_text())
    if pj.get('name') != 'dynatrace':
        errors.append(f'.cursor-plugin/plugin.json name is \"{pj.get(\"name\")}\" not \"dynatrace\"')

# --- Check marketplace.json ---
mp_path = root / '.claude-plugin' / 'marketplace.json'
if not mp_path.exists():
    errors.append('Missing .claude-plugin/marketplace.json')
else:
    mp = json.loads(mp_path.read_text())
    plugins = mp.get('plugins', [])
    dynatrace_plugin = next((p for p in plugins if p.get('name') == 'dynatrace'), None)
    if dynatrace_plugin is None:
        errors.append('marketplace.json does not reference the \"dynatrace\" plugin')
    elif not dynatrace_plugin.get('source', '').startswith('./'):
        errors.append(f'Plugin source should start with ./ but is: {dynatrace_plugin.get(\"source\")}')

# --- Check .antigravity-plugin/plugin.json ---
ag_plugin_path = root / '.antigravity-plugin' / 'plugin.json'
if not ag_plugin_path.exists():
    errors.append('Missing .antigravity-plugin/plugin.json')
else:
    pj = json.loads(ag_plugin_path.read_text())
    if pj.get('name') != 'dynatrace':
        errors.append(f'.antigravity-plugin/plugin.json name is \"{pj.get(\"name\")}\" not \"dynatrace\"')
    for field in ('displayName', 'description', 'version', 'author', 'logo'):
        if not pj.get(field):
            errors.append(f'.antigravity-plugin/plugin.json is missing \"{field}\" (required for the Marketplace)')
    # logo is relative to the plugin root (the repo root), not to .antigravity-plugin/
    if pj.get('logo') and not (root / pj['logo']).exists():
        errors.append(f'.antigravity-plugin/plugin.json logo {pj[\"logo\"]} does not exist')
    prompts = pj.get('suggestedPrompts', [])
    if not prompts or len(prompts) > 3:
        errors.append(f'.antigravity-plugin/plugin.json needs 1-3 suggestedPrompts, has {len(prompts)}')

# --- Check mcp_config.json (Antigravity MCP config) ---
import re
ag_mcp_path = root / 'mcp_config.json'
if not ag_mcp_path.exists():
    errors.append('Missing mcp_config.json')
else:
    servers = json.loads(ag_mcp_path.read_text()).get('mcpServers', {})
    server = servers.get('dynatrace')
    if server is None:
        errors.append('mcp_config.json does not define the \"dynatrace\" server')
    else:
        if 'serverUrl' not in server or 'url' in server or 'type' in server:
            errors.append('mcp_config.json dynatrace server must use \"serverUrl\" (not \"url\"/\"type\")')
        declared = {v.get('name') for v in server.get('variables', [])}
        used = set(re.findall(r'\\$\\{([A-Za-z_][A-Za-z0-9_]*)\\}', json.dumps(server)))
        for name in sorted(used - declared):
            errors.append(f'mcp_config.json uses \${{{name}}} without declaring it in \"variables\"')

if errors:
    for e in errors:
        print(f'FAIL: {e}', file=sys.stderr)
    sys.exit(1)

print(f'  {len(disk_skills)} skills on disk')
print('  .claude-plugin/plugin.json valid')
print('  .cursor-plugin/plugin.json valid')
print('  marketplace.json valid')
print('  .antigravity-plugin/plugin.json valid')
print('  mcp_config.json valid')
"

echo "PASS: test-structure.sh"
