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


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "Usage: python -m repo.tools.validate_episode_continuity_pack path/to/episode_continuity_pack.v1.json",
            file=sys.stderr,
        )
        return 1
    target = pathlib.Path(argv[1]).resolve()
    if not target.exists():
        print(f"ERROR: file not found: {target}", file=sys.stderr)
        return 1

    root = _repo_root()
    schema = _load(root / "repo" / "shared" / "episode_continuity_pack.v1.schema.json")
    data = _load(target)
    try:
        validate(instance=data, schema=schema)
    except ValidationError as ex:
        print(f"SCHEMA_ERROR: {ex.message}", file=sys.stderr)
        return 1

    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
