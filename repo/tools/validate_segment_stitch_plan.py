#!/usr/bin/env python3
"""
validate_segment_stitch_plan.py

Validates segment_stitch_plan.v1 schema and deterministic semantic constraints.

Usage:
  python -m repo.tools.validate_segment_stitch_plan \
    repo/examples/segment_stitch_plan.v1.example.json
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
    raise SystemExit(1)


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _semantic_validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    constraints = data.get("constraints", {})
    max_len = float(constraints.get("max_shot_length_sec", 0.0))
    if max_len > 3.0:
        errors.append("constraints.max_shot_length_sec must be <= 3")

    segments = data.get("segments", [])
    if not isinstance(segments, list) or not segments:
        return errors

    seg_by_id: dict[str, dict[str, Any]] = {}
    orders: list[int] = []
    starts: list[float] = []
    for i, seg in enumerate(segments):
        seg_id = str(seg.get("segment_id", ""))
        order = int(seg.get("order", 0))
        start = float(seg.get("start_sec", 0.0))
        end = float(seg.get("end_sec", 0.0))
        if end <= start:
            errors.append(f"segments[{i}].end_sec must be > start_sec")
        if (end - start) > max_len:
            errors.append(
                f"segments[{i}] duration must be <= constraints.max_shot_length_sec"
            )
        seg_by_id[seg_id] = seg
        orders.append(order)
        starts.append(start)

    if sorted(orders) != list(range(1, len(orders) + 1)):
        errors.append("segments.order must be a contiguous 1..N sequence")

    if starts != sorted(starts):
        errors.append("segments.start_sec must be non-decreasing by listed order")

    stitch_order = data.get("stitch_order", [])
    if isinstance(stitch_order, list):
        seg_ids = [
            str(s.get("segment_id", "")) for s in segments if isinstance(s, dict)
        ]
        if sorted(stitch_order) != sorted(seg_ids):
            errors.append("stitch_order must contain exactly all segment_ids")

    for i, seg in enumerate(segments):
        seam = seg.get("seam")
        if not isinstance(seam, dict):
            continue
        prev = seam.get("prev_segment_id")
        if isinstance(prev, str) and prev and prev not in seg_by_id:
            errors.append(
                f"segments[{i}].seam.prev_segment_id must reference an existing segment_id"
            )

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        eprint(
            "Usage: python -m repo.tools.validate_segment_stitch_plan path/to/segment_stitch_plan.v1.json"
        )
        return 1

    target = pathlib.Path(argv[1]).resolve()
    if not target.exists():
        eprint(f"ERROR: file not found: {target}")
        return 1

    root = _repo_root()
    schema = _load(root / "repo" / "shared" / "segment_stitch_plan.v1.schema.json")
    data = _load(target)

    try:
        validate(instance=data, schema=schema)
    except ValidationError as ex:
        eprint("SCHEMA_ERROR:", ex.message)
        return 1

    semantic_errors = _semantic_validate(data)
    if semantic_errors:
        eprint("SEMANTIC_ERROR:")
        for err in semantic_errors:
            eprint(f"- {err}")
        return 1

    print(f"OK: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
