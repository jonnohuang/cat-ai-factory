#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Dict

try:
    from jsonschema import ValidationError, validate
except Exception:
    print("ERROR: jsonschema not installed in active environment.", file=sys.stderr)
    raise SystemExit(1)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return data


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Validate captions_artifact.v1 contract"
    )
    parser.add_argument("path", help="Path to captions_artifact.v1 JSON")
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    schema = _load(root / "repo" / "shared" / "captions_artifact.v1.schema.json")
    doc = _load(pathlib.Path(args.path).resolve())

    try:
        validate(instance=doc, schema=schema)
    except ValidationError as ex:
        print("INVALID: captions_artifact.v1", file=sys.stderr)
        print(f"- {ex.message}", file=sys.stderr)
        return 1

    print(f"OK: {pathlib.Path(args.path).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
