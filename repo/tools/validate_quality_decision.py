#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

try:
    from jsonschema import ValidationError, validate
except Exception:
    ValidationError = Exception
    validate = None


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        eprint("Usage: python -m repo.tools.validate_quality_decision path/to/quality_decision.v1.json")
        return 1
    target = pathlib.Path(argv[1]).resolve()
    if not target.exists():
        eprint(f"ERROR: file not found: {target}")
        return 1

    root = _repo_root()
    schema = _load(root / "repo" / "shared" / "quality_decision.v1.schema.json")
    data = _load(target)

    if validate is not None:
        try:
            validate(instance=data, schema=schema)
        except ValidationError as ex:
            eprint(f"SCHEMA_ERROR: {ex.message}")
            return 1
    elif not isinstance(data, dict):
        eprint("SEMANTIC_ERROR: payload must be object")
        return 1

    max_retries = int(data.get("policy", {}).get("max_retries", 0))
    retry_attempt = int(data.get("policy", {}).get("retry_attempt", 0))
    action = str(data.get("decision", {}).get("action", ""))
    seg_retry = data.get("segment_retry", {}) if isinstance(data, dict) else {}
    seg_mode = str(seg_retry.get("mode", "none")) if isinstance(seg_retry, dict) else "none"
    seg_targets = seg_retry.get("target_segments", []) if isinstance(seg_retry, dict) else []
    if action in {"retry_recast", "retry_motion"} and retry_attempt > max_retries:
        eprint("SEMANTIC_ERROR: retry action requires retry_attempt <= max_retries")
        return 1
    if action == "retry_motion" and seg_mode == "none":
        eprint("SEMANTIC_ERROR: retry_motion requires segment_retry mode != none")
        return 1
    if seg_mode == "retry_selected" and (not isinstance(seg_targets, list) or len(seg_targets) == 0):
        eprint("SEMANTIC_ERROR: retry_selected requires target_segments")
        return 1

    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
