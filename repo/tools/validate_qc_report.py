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


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        eprint("Usage: python -m repo.tools.validate_qc_report path/to/qc_report.v1.json")
        return 1
    target = pathlib.Path(argv[1]).resolve()
    if not target.exists():
        eprint(f"ERROR: file not found: {target}")
        return 1

    root = _repo_root()
    schema = _load(root / "repo" / "shared" / "qc_report.v1.schema.json")
    data = _load(target)
    try:
        validate(instance=data, schema=schema)
    except ValidationError as ex:
        eprint(f"SCHEMA_ERROR: {ex.message}")
        return 1

    gate_ids = [g.get("gate_id") for g in data.get("gates", []) if isinstance(g, dict)]
    failed_gate_ids = data.get("overall", {}).get("failed_gate_ids", [])
    if not isinstance(failed_gate_ids, list):
        eprint("SEMANTIC_ERROR: overall.failed_gate_ids must be list")
        return 1
    missing = [g for g in failed_gate_ids if g not in gate_ids]
    if missing:
        eprint(f"SEMANTIC_ERROR: failed_gate_ids not found in gates: {missing}")
        return 1

    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
