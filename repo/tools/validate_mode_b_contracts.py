#!/usr/bin/env python3
"""
validate_mode_b_contracts.py

Validates Mode B optional planner-side contracts:
- script_plan.v1
- identity_anchor.v1
- storyboard.v1
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


def _load_registry_ids(path: pathlib.Path, key: str, id_field: str) -> set[str]:
    data = _load(path)
    rows = data.get(key, [])
    out: set[str] = set()
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                rid = row.get(id_field)
                if isinstance(rid, str):
                    out.add(rid)
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate Mode B optional contracts")
    parser.add_argument("--script-plan", required=True, help="Path to script_plan.v1 JSON")
    parser.add_argument("--identity-anchor", required=True, help="Path to identity_anchor.v1 JSON")
    parser.add_argument("--storyboard", required=True, help="Path to storyboard.v1 JSON")
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    script_schema = _load(root / "repo" / "shared" / "script_plan.v1.schema.json")
    anchor_schema = _load(root / "repo" / "shared" / "identity_anchor.v1.schema.json")
    board_schema = _load(root / "repo" / "shared" / "storyboard.v1.schema.json")

    script_plan = _load(pathlib.Path(args.script_plan).resolve())
    identity_anchor = _load(pathlib.Path(args.identity_anchor).resolve())
    storyboard = _load(pathlib.Path(args.storyboard).resolve())

    errors: list[str] = []
    for name, data, schema in [
        ("script_plan", script_plan, script_schema),
        ("identity_anchor", identity_anchor, anchor_schema),
        ("storyboard", storyboard, board_schema),
    ]:
        try:
            validate(instance=data, schema=schema)
        except ValidationError as ex:
            errors.append(f"SCHEMA {name}: {ex.message}")

    job_ids = {str(script_plan.get("job_id")), str(identity_anchor.get("job_id")), str(storyboard.get("job_id"))}
    if len(job_ids) != 1:
        errors.append(f"job_id mismatch across Mode B contracts: {sorted(job_ids)}")

    shot_ids = [s["shot_id"] for s in script_plan.get("shots", [])]
    if len(shot_ids) != len(set(shot_ids)):
        errors.append("script_plan.shots contains duplicate shot_id values")

    anchor_ids = [a["anchor_id"] for a in identity_anchor.get("anchors", [])]
    if len(anchor_ids) != len(set(anchor_ids)):
        errors.append("identity_anchor.anchors contains duplicate anchor_id values")
    anchor_set = set(anchor_ids)
    shot_set = set(shot_ids)

    for idx, frame in enumerate(storyboard.get("frames", [])):
        if frame["shot_id"] not in shot_set:
            errors.append(f"storyboard.frames[{idx}] references unknown shot_id '{frame['shot_id']}'")
        if frame["anchor_id"] not in anchor_set:
            errors.append(f"storyboard.frames[{idx}] references unknown anchor_id '{frame['anchor_id']}'")

    hero_ids = _load_registry_ids(root / "repo" / "shared" / "hero_registry.v1.json", "heroes", "hero_id")
    style_ids = _load_registry_ids(root / "repo" / "shared" / "style_registry.v1.json", "styles", "style_id")
    for idx, anchor in enumerate(identity_anchor.get("anchors", [])):
        if anchor["hero_id"] not in hero_ids:
            errors.append(f"identity_anchor.anchors[{idx}] hero_id not found in hero registry: {anchor['hero_id']}")
        if anchor["style_id"] not in style_ids:
            errors.append(f"identity_anchor.anchors[{idx}] style_id not found in style registry: {anchor['style_id']}")

    if errors:
        print("INVALID: Mode B contracts", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    print("OK: Mode B contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
