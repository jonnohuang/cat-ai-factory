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


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        eprint("Usage: python -m repo.tools.validate_retry_attempt_lineage path/to/retry_attempt_lineage.v1.json")
        return 1
    target = pathlib.Path(argv[1]).resolve()
    if not target.exists():
        eprint(f"ERROR: file not found: {target}")
        return 1

    root = _repo_root()
    schema = _load(root / "repo" / "shared" / "retry_attempt_lineage.v1.schema.json")
    data = _load(target)
    try:
        validate(instance=data, schema=schema)
    except ValidationError as ex:
        eprint(f"SCHEMA_ERROR: {ex.message}")
        return 1

    attempts = data.get("attempts", []) if isinstance(data, dict) else []
    if not isinstance(attempts, list) or len(attempts) == 0:
        eprint("SEMANTIC_ERROR: attempts must contain at least one entry")
        return 1

    for i, item in enumerate(attempts):
        if not isinstance(item, dict):
            eprint(f"SEMANTIC_ERROR: attempt[{i}] must be an object")
            return 1
        resolution = str(item.get("resolution", ""))
        retry_type = item.get("retry_type")
        if resolution == "retry" and retry_type not in {"motion", "recast"}:
            eprint(f"SEMANTIC_ERROR: attempt[{i}] retry resolution requires retry_type motion/recast")
            return 1
        if resolution == "finalize" and retry_type not in {"none", None}:
            eprint(f"SEMANTIC_ERROR: attempt[{i}] finalize resolution requires retry_type none/null")
            return 1
        if resolution == "escalate" and retry_type not in {"none", None}:
            eprint(f"SEMANTIC_ERROR: attempt[{i}] escalate resolution requires retry_type none/null")
            return 1

    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
