#!/usr/bin/env python3
"""
Validates a Cat AI Factory series_bible.v1.json against its schema.
Performs semantic checks:
- Schema validation
- Cross-reference check with hero_registry.v1.json (canon.default_cast)
- Uniqueness checks (gag_id, setting_id)

Usage:
  python3 repo/tools/validate_series_bible.py path/to/series_bible.v1.json [path/to/hero_registry.v1.json]

Exit codes:
  0 = valid
  1 = invalid / error
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Set

# Robustly find the repo root
_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_TOOL_DIR, "..", ".."))

# Add _REPO_ROOT to sys.path
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


# Fail-loud import for jsonschema
try:
    from jsonschema import ValidationError, validate
except ImportError:
    eprint("ERROR: jsonschema not installed.")
    eprint("Please run: pip install jsonschema")
    sys.exit(1)


def load_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        eprint(f"ERROR: File not found: {path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        eprint(f"ERROR: Invalid JSON in {path}: {e}")
        sys.exit(1)
    except Exception as e:
        eprint(f"ERROR: Could not read {path}: {e}")
        sys.exit(1)


def validate_references(bible_data: Dict[str, Any], registry_path: str) -> bool:
    ok = True

    # Load registry
    registry_data = load_json(registry_path)

    # Registry identity check (optional but helpful)
    if (
        registry_data.get("project") != "Cat AI Factory"
        or registry_data.get("schema") != "hero_registry.v1"
    ):
        eprint(
            f"SEMANTIC_ERROR: Registry at {registry_path} appears to be invalid (wrong project or schema)."
        )
        # We continue, but it's suspicious.

    # Registry shape check
    heroes = registry_data.get("heroes")
    if not isinstance(heroes, list):
        eprint(
            f"SEMANTIC_ERROR: Invalid registry format in {registry_path}: 'heroes' must be a list"
        )
        return False

    # Extract hero IDs from registry
    hero_ids: Set[str] = {h.get("hero_id", "") for h in heroes if isinstance(h, dict)}
    hero_ids.discard("")  # remove any empty strings if malformed

    ok = True

    # Check canon.default_cast
    if "canon" in bible_data and "default_cast" in bible_data["canon"]:
        for i, hero_ref in enumerate(bible_data["canon"]["default_cast"]):
            if hero_ref not in hero_ids:
                eprint(
                    f"SEMANTIC_ERROR: canon.default_cast[{i}] '{hero_ref}' not found in registry {registry_path}"
                )
                ok = False

    # Check gag_id uniqueness
    if "running_gags" in bible_data:
        gag_ids = set()
        for i, gag in enumerate(bible_data["running_gags"]):
            if not isinstance(gag, dict):
                eprint(f"SEMANTIC_ERROR: running_gags[{i}] is not an object")
                ok = False
                continue

            gid = gag.get("gag_id")
            if gid in gag_ids:
                eprint(f"SEMANTIC_ERROR: duplicate gag_id '{gid}' at running_gags[{i}]")
                ok = False
            if gid:
                gag_ids.add(gid)

    # Check setting_id uniqueness
    if "settings" in bible_data:
        setting_ids = set()
        for i, setting in enumerate(bible_data["settings"]):
            if not isinstance(setting, dict):
                eprint(f"SEMANTIC_ERROR: settings[{i}] is not an object")
                ok = False
                continue

            sid = setting.get("setting_id")
            if sid in setting_ids:
                eprint(f"SEMANTIC_ERROR: duplicate setting_id '{sid}' at settings[{i}]")
                ok = False
            if sid:
                setting_ids.add(sid)

    return ok


def main(argv: List[str]) -> int:
    if len(argv) < 2 or len(argv) > 3:
        eprint(
            "Usage: python3 repo/tools/validate_series_bible.py path/to/series_bible.v1.json [path/to/hero_registry.v1.json]"
        )
        return 1

    bible_path = argv[1]

    # Default registry path relative to repo root if not provided
    if len(argv) == 3:
        registry_path = argv[2]
    else:
        registry_path = os.path.join(
            _REPO_ROOT, "repo", "shared", "hero_registry.v1.json"
        )

    # 1. Load schema
    schema_path = os.path.join(
        _REPO_ROOT, "repo", "shared", "series_bible.v1.schema.json"
    )
    schema = load_json(schema_path)

    # 2. Load bible
    bible_data = load_json(bible_path)

    # 3. Validate schema
    try:
        validate(instance=bible_data, schema=schema)
    except ValidationError as e:
        eprint(f"Schema Validation Error in {bible_path}:")
        eprint(f"Message: {e.message}")
        if e.path:
            eprint(f"Path: {' -> '.join(str(p) for p in e.path)}")
        else:
            eprint("Path: (root)")
        return 1

    # 4. Validate references (logic in script for now, as semantic check)
    if not validate_references(bible_data, registry_path):
        eprint(f"Semantic Validation Failed for {bible_path}")
        return 1

    print(f"OK: {bible_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
