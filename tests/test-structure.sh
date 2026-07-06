#!/usr/bin/env bash
set -euo pipefail
# Test: Validate structural consistency between skills/, plugin manifests, and marketplace.json.
#
# Checks:
#   1. Every skill dir has SKILL.md
#   2. .claude-plugin/plugin.json exists and has name "dynatrace"
#   3. .cursor-plugin/plugin.json exists and has name "dynatrace"
#   4. marketplace.json is valid, references the dynatrace plugin, source uses ./ prefix

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

if errors:
    for e in errors:
        print(f'FAIL: {e}', file=sys.stderr)
    sys.exit(1)

print(f'  {len(disk_skills)} skills on disk')
print('  .claude-plugin/plugin.json valid')
print('  .cursor-plugin/plugin.json valid')
print('  marketplace.json valid')
"

echo "PASS: test-structure.sh"
