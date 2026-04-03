#!/usr/bin/env bash
set -euo pipefail
# Test: Validate SKILL.md quality across all skills.
#
# Checks:
#   1. Every SKILL.md has required frontmatter fields: name, description, license
#   2. Skill name matches parent directory name
#   3. Skill name is valid kebab-case, max 64 chars
#   4. Description is ≤250 chars (Claude Code truncation threshold)
#   5. Description is ≤1024 chars (Agent Skills spec hard limit)
#   6. No trailing whitespace in frontmatter fields

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== test-skill-quality.sh ==="

python3 -c "
import re, sys, pathlib

root = pathlib.Path('$ROOT_DIR')
skills_dir = root / 'skills'
errors = []
warnings = []

def parse_frontmatter(text):
    m = re.search(r'^---\s*\n(.*?)\n---\s*', text, re.DOTALL)
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        if ':' not in line or line.strip().startswith('#'):
            continue
        key, value = line.split(':', 1)
        data[key.strip()] = value.strip()
    return data

for skill_dir in sorted(skills_dir.iterdir()):
    if not skill_dir.is_dir() or not skill_dir.name.startswith('dt-'):
        continue
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.exists():
        errors.append(f'{skill_dir.name}: missing SKILL.md')
        continue

    text = skill_md.read_text(encoding='utf-8')
    fm = parse_frontmatter(text)
    name = skill_dir.name

    # 1. Required fields
    for field in ('name', 'description', 'license'):
        if field not in fm or not fm[field]:
            errors.append(f'{name}: missing required frontmatter field \"{field}\"')

    if 'name' not in fm:
        continue

    fm_name = fm['name']
    fm_desc = fm.get('description', '')

    # 2. Name matches directory
    if fm_name != name:
        errors.append(f'{name}: frontmatter name \"{fm_name}\" does not match directory name')

    # 3. Name format: kebab-case, max 64 chars
    if not re.match(r'^[a-z0-9][a-z0-9-]*$', fm_name):
        errors.append(f'{name}: name \"{fm_name}\" is not valid kebab-case')
    if len(fm_name) > 64:
        errors.append(f'{name}: name exceeds 64 chars ({len(fm_name)})')

    # 4. Description ≤250 chars (Claude Code truncation warning)
    if len(fm_desc) > 250:
        warnings.append(f'{name}: description is {len(fm_desc)} chars, exceeds 250 (Claude Code truncates in plugin listing)')

    # 5. Description ≤1024 chars (Agent Skills spec hard limit)
    if len(fm_desc) > 1024:
        errors.append(f'{name}: description is {len(fm_desc)} chars, exceeds Agent Skills spec limit of 1024')

    # 6. Trailing whitespace in frontmatter
    m = re.search(r'^---\s*\n(.*?)\n---\s*', text, re.DOTALL)
    if m:
        for i, line in enumerate(m.group(1).splitlines(), 1):
            if line != line.rstrip():
                warnings.append(f'{name}: trailing whitespace in frontmatter line {i}')

if warnings:
    for w in warnings:
        print(f'WARNING: {w}')

if errors:
    for e in errors:
        print(f'FAIL: {e}', file=sys.stderr)
    sys.exit(1)

print('  All skill quality checks passed')
"

echo "PASS: test-skill-quality.sh"
