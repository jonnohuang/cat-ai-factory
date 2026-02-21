#!/usr/bin/env python3
"""
validate_recast_quality_report.py

Validate recast_quality_report.v1 output against schema with semantic checks.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

try:
    from jsonschema import ValidationError, validate
except Exception:
    print("ERROR: jsonschema not installed in active environment.", file=sys.stderr)
    raise SystemExit(1)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate recast_quality_report.v1")
    parser.add_argument("file", help="Path to recast_quality_report.v1.json")
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    report = _load(pathlib.Path(args.file).resolve())
    schema = _load(root / "repo" / "shared" / "recast_quality_report.v1.schema.json")

    errors: list[str] = []
    try:
        validate(instance=report, schema=schema)
    except ValidationError as ex:
        errors.append(f"SCHEMA: {ex.message}")

    failed = set(report.get("overall", {}).get("failed_metrics", []))
    metrics = report.get("metrics", {})
    for name in (
        "identity_consistency",
        "mask_edge_bleed",
        "temporal_stability",
        "loop_seam",
        "audio_video",
    ):
        row = metrics.get(name, {})
        passed = bool(row.get("pass"))
        if (not passed) and (name not in failed):
            errors.append(
                f"{name} has pass=false but is missing from overall.failed_metrics"
            )
        if passed and (name in failed):
            errors.append(f"{name} has pass=true but appears in overall.failed_metrics")

    if errors:
        print("INVALID: recast quality report", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    print("OK: recast quality report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
