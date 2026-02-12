#!/usr/bin/env python3
"""
validate_hero_registry.py

Validates a Cat AI Factory hero_registry.v1.json against its schema.
Performs semantic checks:
- Unique hero_id

Usage:
  python3 repo/tools/validate_hero_registry.py path/to/hero_registry.v1.json

Exit codes:
  0 = valid
  1 = invalid / error
"""
from __future__ import annotations

import os
import sys
from typing import Any, List


# Robustly find the repo root
# This script is at repo/tools/validate_hero_registry.py
_TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_TOOL_DIR, "..", ".."))

# Add _REPO_ROOT to sys.path so we can do absolute imports like 'from repo.shared...'
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Schema is sibling to tools in repo/shared
SCHEMA_PATH = os.path.normpath(os.path.join(_TOOL_DIR, "..", "shared", "hero_registry.v1.schema.json"))


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        eprint("Usage: python3 repo/tools/validate_hero_registry.py path/to/registry.json")
        return 1

    registry_path = argv[1]
    
    # 2. Use shared validator
    try:
        from repo.shared.hero_registry_validate import validate_registry_file
        
        ok, errors = validate_registry_file(registry_path, SCHEMA_PATH)
        if not ok:
            eprint(f"INVALID: {registry_path}")
            for e in errors:
                eprint(f"- {e}")
            return 1

    except ImportError as ie:
        eprint(f"ERROR: Failed to import shared validator: {ie}")
        return 1
    except Exception as ex:
        eprint(f"ERROR: Unexpected validation error: {ex}")
        return 1

    print(f"OK: {registry_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
