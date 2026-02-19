#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

try:
    from jsonschema import ValidationError, validate
except Exception:
    print("ERROR: jsonschema not installed", file=sys.stderr)
    raise SystemExit(1)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python -m repo.tools.validate_pointer_resolution <path>", file=sys.stderr)
        return 1
    
    target = pathlib.Path(argv[1]).resolve()
    root = _repo_root()
    schema_path = root / "repo" / "shared" / "pointer_resolution.v1.schema.json"
    
    validate(instance=json.loads(target.read_text(encoding="utf-8")), schema=json.loads(schema_path.read_text(encoding="utf-8")))
    print(f"OK: {target}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))