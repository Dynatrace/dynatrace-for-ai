# Analyze MZ and auto-tagging exports (offline)

Offline companion to the live-tenant classifier [evaluate-and-classify.md](evaluate-and-classify.md). Use this when you have exported JSON files but no live tenant connection. Works from `*.builtin_management-zones.json` and `*.builtin_tags.auto-tagging.json` exports obtained from the Settings API or the Dynatrace UI.

For live-tenant analysis (dtctl required), use [evaluate-and-classify.md](evaluate-and-classify.md).

## Contents

- [What it produces](#what-it-produces)
- [Script](#script)
- [Usage](#usage)
- [Cross-referencing in Python](#cross-referencing-in-python)
- [Edge cases handled](#edge-cases-handled)
- [Related references](#related-references)

## What it produces

| Output | What it contains |
|---|---|
| **MZ inventory** | One record per zone: name, objectId, rule count, rule types (ME/DIMENSION/SELECTOR), entity types, condition keys, and every tag string referenced in tag conditions and entity selectors |
| **Auto-tag index** | `{rule_name → objectId}` lookup built from the auto-tagging export |
| **Cross-reference** | Which auto-tagging rules are load-bearing for MZ entity selection (matched), and which tag references in MZ conditions have no corresponding auto-tagging rule (unmatched — cloud tags, Keptn tags, manual tags) |

## Script

Save as `parse_exports.py` and run from the directory containing your export files.

```python
"""
parse_exports.py — offline loader for MZ and auto-tagging exports.

Functions:
  build_mz_inventory(mz_list)      → flat inventory (one dict per zone)
  build_autotag_index(autotag_list) → {rule_name: objectId} lookup

CLI:
  python parse_exports.py --mz-file <path> [--autotag-file <path>] [--output inventory|index|both]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def load_json(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    with p.open(encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {p}: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {p}, got {type(data).__name__}")
    return data


def _extract_tag_strings(rules: list[dict[str, Any]]) -> list[str]:
    """Collect every tag string from _TAGS conditions and tag("...") selectors."""
    tags: list[str] = []
    for rule in rules:
        if rule.get("type") == "ME":
            for cond in rule.get("attributeRule", {}).get("conditions", []):
                if cond.get("key", "").endswith("_TAGS") and "tag" in cond:
                    tags.append(cond["tag"])
        elif rule.get("type") == "SELECTOR":
            selector = rule.get("entitySelector", "")
            tags.extend(re.findall(r'tag\("([^"]+)"\)', selector))
    return tags


def build_mz_inventory(mz_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a flat inventory from a parsed management-zones JSON array.

    Each record contains:
      name           human-readable zone name  (value.name)
      objectId       stable settings UID
      rule_count     total number of rules
      rule_types     set of types present: ME, DIMENSION, SELECTOR
      entity_types   entity types from ME rules (SERVICE, HOST, ...)
      condition_keys condition key names from ME rules (SERVICE_TAGS, ...)
      tag_refs       every tag string from _TAGS conditions and tag("...") selectors
    """
    inventory: list[dict[str, Any]] = []
    for mz in mz_list:
        value = mz.get("value", {})
        rules = value.get("rules", [])
        rule_types: set[str] = set()
        entity_types: set[str] = set()
        condition_keys: set[str] = set()
        for rule in rules:
            rtype = rule.get("type", "")
            rule_types.add(rtype)
            if rtype == "ME":
                attr = rule.get("attributeRule", {})
                entity_types.add(attr.get("entityType", ""))
                for cond in attr.get("conditions", []):
                    key = cond.get("key", "")
                    if key:
                        condition_keys.add(key)
        inventory.append({
            "name": value.get("name", ""),
            "objectId": mz.get("objectId", ""),
            "rule_count": len(rules),
            "rule_types": rule_types,
            "entity_types": entity_types,
            "condition_keys": condition_keys,
            "tag_refs": _extract_tag_strings(rules),
        })
    return inventory


def build_autotag_index(autotag_list: list[dict[str, Any]]) -> dict[str, str]:
    """Build a {rule_name: objectId} lookup from a parsed auto-tagging JSON array.

    Use case-insensitive fallback at lookup time when an exact match is not found.
    """
    return {
        item["value"]["name"]: item["objectId"]
        for item in autotag_list
        if "value" in item and "name" in item["value"] and "objectId" in item
    }


def _to_serialisable(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for record in inventory:
        row = dict(record)
        row["rule_types"] = sorted(record["rule_types"])
        row["entity_types"] = sorted(record["entity_types"])
        row["condition_keys"] = sorted(record["condition_keys"])
        result.append(row)
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Parse Dynatrace MZ and auto-tagging export files.")
    parser.add_argument("--mz-file", type=Path, metavar="PATH")
    parser.add_argument("--autotag-file", type=Path, metavar="PATH")
    parser.add_argument("--output", choices=["inventory", "index", "both"], default="both")
    args = parser.parse_args(argv)

    want_inventory = args.output in ("inventory", "both")
    want_index = args.output in ("index", "both")
    if want_inventory and args.mz_file is None:
        parser.error("--mz-file is required for inventory output.")
    if want_index and args.autotag_file is None:
        parser.error("--autotag-file is required for index output.")

    result: dict[str, Any] = {}
    if want_inventory:
        inventory = build_mz_inventory(load_json(args.mz_file))
        result["inventory"] = _to_serialisable(inventory)
        if not want_index:
            result["summary"] = {
                "total_zones": len(inventory),
                "empty_rules": sum(1 for r in inventory if r["rule_count"] == 0),
            }
    if want_index:
        index = build_autotag_index(load_json(args.autotag_file))
        result["autotag_index"] = index
        if not want_inventory:
            result["summary"] = {"total_rules": len(index)}

    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
```

## Usage

```bash
# MZ inventory only
python parse_exports.py --mz-file tenant.builtin_management-zones.json --output inventory

# Auto-tag index only
python parse_exports.py --autotag-file tenant.builtin_tags.auto-tagging.json --output index

# Both (cross-reference input)
python parse_exports.py \
  --mz-file tenant.builtin_management-zones.json \
  --autotag-file tenant.builtin_tags.auto-tagging.json \
  --output both
```

Output is JSON to stdout. Pipe to `jq` or redirect to a file.

## Cross-referencing in Python

```python
from parse_exports import load_json, build_mz_inventory, build_autotag_index

inventory  = build_mz_inventory(load_json("tenant.builtin_management-zones.json"))
at_index   = build_autotag_index(load_json("tenant.builtin_tags.auto-tagging.json"))
lower_index = {k.lower(): (k, v) for k, v in at_index.items()}

matched   = []  # auto-tag rules load-bearing for MZ entity selection
unmatched = []  # tag refs with no corresponding auto-tag rule

for zone in inventory:
    for tag_str in zone["tag_refs"]:
        # Strip cloud-origin tags — not auto-tagging rules
        if re.match(r'^\[(AWS|GCP|Azure)\]', tag_str):
            unmatched.append({"zone": zone["name"], "tag": tag_str, "source": "cloud"})
            continue
        rule_name = tag_str.split(":")[0]
        if rule_name in at_index:
            matched.append({"rule": rule_name, "objectId": at_index[rule_name], "zone": zone["name"]})
        elif rule_name.lower() in lower_index:
            original, oid = lower_index[rule_name.lower()]
            matched.append({"rule": original, "objectId": oid, "zone": zone["name"], "note": "case-insensitive match"})
        else:
            unmatched.append({"zone": zone["name"], "tag": tag_str, "source": "unknown"})
```

## Edge cases handled

- **Empty `rules` arrays** — zones with no rules are included in the inventory with `rule_count: 0`; `tag_refs` is `[]`
- **Cloud-origin tags** (`[AWS]...`, `[GCP]...`, `[Azure]...`) — extracted into `tag_refs` but should be excluded from auto-tag cross-reference (not auto-tagging rules)
- **Case sensitivity** — exact match first, then case-insensitive fallback; discrepancies are flagged
- **SELECTOR `tag("...")` extraction** — regex-based; works for standard selector strings
- **Sets vs lists** — `rule_types`, `entity_types`, `condition_keys` are Python sets internally; CLI output converts them to sorted lists for JSON serialization

## Related references

- [mz-export-schema.md](mz-export-schema.md) — export file structure the script parses (rule types, condition keys, tag formats)
- [mz-classification.md](mz-classification.md) — classify the parsed zones with the 7-dimension taxonomy
- [management-zones.md](management-zones.md) — management zone migration strategy and runbook
- [autotagging.md](../autotagging/autotagging.md) — source-side migration for the auto-tagging rules the cross-reference surfaces
