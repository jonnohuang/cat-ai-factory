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
        eprint(
            "Usage: python -m repo.tools.validate_finalize_gate path/to/finalize_gate.v1.json"
        )
        return 1

    target = pathlib.Path(argv[1]).resolve()
    if not target.exists():
        eprint(f"ERROR: file not found: {target}")
        return 1

    root = _repo_root()
    schema = _load(root / "repo" / "shared" / "finalize_gate.v1.schema.json")
    data = _load(target)
    try:
        validate(instance=data, schema=schema)
    except ValidationError as ex:
        eprint(f"SCHEMA_ERROR: {ex.message}")
        return 1

    gate = data.get("gate", {}) if isinstance(data, dict) else {}
    src = data.get("source", {}) if isinstance(data, dict) else {}
    allow_finalize = bool(gate.get("allow_finalize"))
    status = str(gate.get("status", ""))
    action = str(src.get("decision_action", ""))

    expected_allow = action == "proceed_finalize"
    expected_status = "pass" if expected_allow else "block"
    if allow_finalize != expected_allow:
        eprint("SEMANTIC_ERROR: gate.allow_finalize must match source decision action")
        return 1
    if status != expected_status:
        eprint("SEMANTIC_ERROR: gate.status must match allow_finalize")
        return 1

    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
