#!/usr/bin/env python3
"""
Validates a Cat AI Factory audio_manifest.v1.json against its schema.
Performs semantic checks:
- Schema validation
- Uniqueness checks (bed.id)
- Path safety checks (relpath must be sandbox-relative assets/audio/)

Usage:
  python3 repo/tools/validate_audio_manifest.py sandbox/assets/audio/audio_manifest.v1.json

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


def validate_semantics(manifest_data: Dict[str, Any]) -> bool:
    ok = True

    # Identity check
    if (
        manifest_data.get("project") != "Cat AI Factory"
        or manifest_data.get("schema") != "audio_manifest.v1"
    ):
        eprint(
            "SEMANTIC_ERROR: Manifest appears to be invalid (wrong project or schema)."
        )
        ok = False

    beds = manifest_data.get("beds", [])
    if not isinstance(beds, list):
        eprint("ERROR: 'beds' must be a list")
        return False

    seen_ids = set()

    for i, bed in enumerate(beds):
        if not isinstance(bed, dict):
            eprint(f"SEMANTIC_ERROR: beds[{i}] is not an object")
            ok = False
            continue

        # Check ID uniqueness
        bid = bed.get("id")
        if bid is not None:
            if not isinstance(bid, str):
                eprint(f"SEMANTIC_ERROR: beds[{i}].id must be a string")
                ok = False
            elif bid in seen_ids:
                eprint(f"SEMANTIC_ERROR: duplicate bed id '{bid}' at beds[{i}]")
                ok = False
            else:
                seen_ids.add(bid)

        # Check relpath
        relpath = bed.get("relpath")
        if relpath:
            if not isinstance(relpath, str):
                eprint(f"SEMANTIC_ERROR: beds[{i}].relpath must be a string")
                ok = False
                continue

            # Normalize path (handle Windows separators and .. resolution)
            norm_rel = os.path.normpath(relpath).replace("\\", "/")

            # Must not be absolute
            if os.path.isabs(norm_rel) or norm_rel.startswith("/"):
                eprint(
                    f"SEMANTIC_ERROR: beds[{i}].relpath '{relpath}' must not be absolute"
                )
                ok = False

            # Must not contain traversal (check segments)
            path_segments = norm_rel.split("/")
            if ".." in path_segments:
                eprint(
                    f"SEMANTIC_ERROR: beds[{i}].relpath '{relpath}' must not contain path traversal (..)"
                )
                ok = False

            # Must start with assets/audio/
            if not norm_rel.startswith("assets/audio/"):
                eprint(
                    f"SEMANTIC_ERROR: beds[{i}].relpath '{relpath}' must start with 'assets/audio/'"
                )
                ok = False

    return ok


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        eprint(
            "Usage: python3 repo/tools/validate_audio_manifest.py sandbox/assets/audio/audio_manifest.v1.json"
        )
        return 1

    manifest_path = argv[1]

    # 1. Load schema
    schema_path = os.path.join(
        _REPO_ROOT, "sandbox", "assets", "audio", "audio_manifest.v1.schema.json"
    )
    schema = load_json(schema_path)

    # 2. Load manifest
    manifest_data = load_json(manifest_path)

    # 3. Validate schema
    try:
        validate(instance=manifest_data, schema=schema)
    except ValidationError as e:
        eprint(f"Schema Validation Error in {manifest_path}:")
        eprint(f"Message: {e.message}")
        if e.path:
            eprint(f"Path: {' -> '.join(str(p) for p in e.path)}")
        else:
            eprint("Path: (root)")
        return 1

    # 4. Validate semantics
    if not validate_semantics(manifest_data):
        eprint(f"Semantic Validation Failed for {manifest_path}")
        return 1

    print(f"OK: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
