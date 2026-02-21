#!/usr/bin/env python3
"""
validate_video_analysis.py

Validates a Video Analyzer metadata artifact against schema and semantic timing rules.

Usage:
  python -m repo.tools.validate_video_analysis path/to/video-analysis.json

Exit codes:
  0 = valid
  1 = invalid / error
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

try:
    from jsonschema import ValidationError, validate
except Exception:
    print("ERROR: jsonschema not installed in active environment.", file=sys.stderr)
    print("Install in Conda env: python -m pip install jsonschema", file=sys.stderr)
    raise SystemExit(1)


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def load_json(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def semantic_validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    loop = data.get("pattern", {}).get("looping", {})
    loop_start = loop.get("loop_start_sec")
    loop_end = loop.get("loop_end_sec")
    if isinstance(loop_start, (int, float)) and isinstance(loop_end, (int, float)):
        if loop_end <= loop_start:
            errors.append(
                "pattern.looping.loop_end_sec must be > pattern.looping.loop_start_sec"
            )

    beats = data.get("pattern", {}).get("choreography", {}).get("beats", [])
    if isinstance(beats, list):
        for i, beat in enumerate(beats):
            start = beat.get("start_sec")
            end = beat.get("end_sec")
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                if end <= start:
                    errors.append(
                        f"pattern.choreography.beats[{i}].end_sec must be > "
                        f"pattern.choreography.beats[{i}].start_sec"
                    )

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        eprint(
            "Usage: python -m repo.tools.validate_video_analysis path/to/video-analysis.json"
        )
        return 1

    target_path = pathlib.Path(argv[1]).resolve()
    if not target_path.exists():
        eprint(f"ERROR: file not found: {target_path}")
        return 1

    schema_path = _repo_root() / "repo" / "shared" / "video_analysis.v1.schema.json"
    if not schema_path.exists():
        eprint(f"ERROR: schema not found: {schema_path}")
        return 1

    try:
        schema = load_json(schema_path)
        data = load_json(target_path)
    except json.JSONDecodeError as ex:
        eprint(f"ERROR: invalid JSON: {ex}")
        return 1
    except OSError as ex:
        eprint(f"ERROR: read failed: {ex}")
        return 1

    try:
        validate(instance=data, schema=schema)
    except ValidationError as ex:
        eprint(f"SCHEMA_ERROR: {target_path}")
        eprint(ex.message)
        if ex.path:
            eprint("Path:", " -> ".join(str(p) for p in ex.path))
        return 1

    semantic_errors = semantic_validate(data)
    if semantic_errors:
        eprint(f"SEMANTIC_ERROR: {target_path}")
        for err in semantic_errors:
            eprint(f"- {err}")
        return 1

    print(f"OK: {target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
