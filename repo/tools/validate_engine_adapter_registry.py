#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys

import jsonschema


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"expected object: {path}")
    return data


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        eprint("Usage: python -m repo.tools.validate_engine_adapter_registry path/to/engine_adapter_registry.v1.json")
        return 2
    root = _repo_root()
    target = root / argv[1]
    if not target.exists():
        eprint(f"ERROR: missing file: {target}")
        return 1
    schema = _load(root / "repo" / "shared" / "engine_adapter_registry.v1.schema.json")
    payload = _load(target)
    jsonschema.validate(instance=payload, schema=schema)
    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
