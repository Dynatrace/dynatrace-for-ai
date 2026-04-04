#!/usr/bin/env bash
set -euo pipefail
# Test: Validate structural consistency between skills/, plugin symlinks, and marketplace.json.
#
# Checks:
#   1. Every skill dir has SKILL.md
#   2. Every skill in skills/ has a corresponding symlink in plugins/dynatrace/skills/
#   3. marketplace.json is valid and references the dynatrace plugin
#   4. marketplace.json source uses ./ prefix

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== test-structure.sh ==="

python3 -c "
import json, sys, os, re, pathlib

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

# --- Check plugin skill symlinks ---
plugin_skills_dir = root / 'plugins' / 'dynatrace' / 'skills'
if plugin_skills_dir.exists():
    linked_skills = set()
    for entry in sorted(plugin_skills_dir.iterdir()):
        if entry.name.startswith('dt-') and entry.is_symlink():
            linked_skills.add(entry.name)

    missing = sorted(disk_skills - linked_skills)
    extra = sorted(linked_skills - disk_skills)
    if missing:
        errors.append(f'Plugin missing skill symlinks: {missing}')
    if extra:
        errors.append(f'Plugin has symlinks to non-existent skills: {extra}')
else:
    errors.append('Missing plugins/dynatrace/skills/ directory')

# --- Check plugin.json ---
plugin_json_path = root / 'plugins' / 'dynatrace' / '.claude-plugin' / 'plugin.json'
if not plugin_json_path.exists():
    errors.append('Missing plugins/dynatrace/.claude-plugin/plugin.json')
else:
    pj = json.loads(plugin_json_path.read_text())
    if pj.get('name') != 'dynatrace':
        errors.append(f'plugin.json name is \"{pj.get(\"name\")}\" not \"dynatrace\"')

# --- Check marketplace.json ---
mp_path = root / '.claude-plugin' / 'marketplace.json'
if not mp_path.exists():
    errors.append('Missing .claude-plugin/marketplace.json')
else:
    mp = json.loads(mp_path.read_text())
    plugins = mp.get('plugins', [])
    dynatrace_plugin = next((plugin for plugin in plugins if plugin.get('name') == 'dynatrace'), None)
    if dynatrace_plugin is None:
        errors.append('marketplace.json does not reference the \"dynatrace\" plugin')
    elif not dynatrace_plugin.get('source', '').startswith('./'):
        errors.append(f'Plugin source should start with ./ but is: {dynatrace_plugin.get(\"source\")}')

if errors:
    for e in errors:
        print(f'FAIL: {e}', file=sys.stderr)
    sys.exit(1)

print(f'  {len(disk_skills)} skills on disk, all linked in plugin')
print('  marketplace.json valid')
"

echo "PASS: test-structure.sh"
