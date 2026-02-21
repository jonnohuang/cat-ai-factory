#!/usr/bin/env python3
"""
validate_viggle_handoff.py

Validates external HITL recast handoff contracts:
- viggle_pack.v1
- external_recast_lifecycle.v1
- viggle_reingest_pointer.v1
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


def _must_exist(path: pathlib.Path, label: str) -> list[str]:
    if not path.exists():
        return [f"{label} not found: {path}"]
    return []


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Viggle HITL handoff contracts"
    )
    parser.add_argument("--pack", required=True, help="Path to viggle_pack.v1 JSON")
    parser.add_argument(
        "--lifecycle", required=True, help="Path to external_recast_lifecycle.v1 JSON"
    )
    parser.add_argument(
        "--pointer", required=True, help="Path to viggle_reingest_pointer.v1 JSON"
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    schemas = {
        "pack": _load(root / "repo" / "shared" / "viggle_pack.v1.schema.json"),
        "lifecycle": _load(
            root / "repo" / "shared" / "external_recast_lifecycle.v1.schema.json"
        ),
        "pointer": _load(
            root / "repo" / "shared" / "viggle_reingest_pointer.v1.schema.json"
        ),
    }
    docs = {
        "pack": _load(pathlib.Path(args.pack).resolve()),
        "lifecycle": _load(pathlib.Path(args.lifecycle).resolve()),
        "pointer": _load(pathlib.Path(args.pointer).resolve()),
    }

    errors: list[str] = []
    for name in ("pack", "lifecycle", "pointer"):
        try:
            validate(instance=docs[name], schema=schemas[name])
        except ValidationError as ex:
            errors.append(f"SCHEMA {name}: {ex.message}")

    job_ids = {
        str(docs["pack"].get("job_id")),
        str(docs["lifecycle"].get("job_id")),
        str(docs["pointer"].get("job_id")),
    }
    if len(job_ids) != 1:
        errors.append(f"job_id mismatch across contracts: {sorted(job_ids)}")

    if docs["lifecycle"].get("reingest_pointer") and docs["lifecycle"][
        "reingest_pointer"
    ] != docs["pointer"].get("inbox_relpath", docs["lifecycle"]["reingest_pointer"]):
        # lifecycle stores canonical path; pointer file may store no self-path.
        pass

    if docs["lifecycle"].get("reingest_result_video") and docs["lifecycle"][
        "reingest_result_video"
    ] != docs["pointer"].get("result_video_relpath"):
        errors.append(
            "lifecycle.reingest_result_video must match pointer.result_video_relpath when both are set"
        )

    pack_dir = pathlib.Path(docs["pack"]["pack_root"])
    errors.extend(_must_exist(root / docs["pack"]["hero_image"], "pack.hero_image"))
    errors.extend(_must_exist(root / docs["pack"]["motion_video"], "pack.motion_video"))
    errors.extend(_must_exist(root / docs["pack"]["prompt_file"], "pack.prompt_file"))
    errors.extend(
        _must_exist(root / docs["pack"]["instructions_file"], "pack.instructions_file")
    )
    if not str(pack_dir).endswith("/viggle_pack"):
        errors.append("pack_root must end with /viggle_pack")

    pointer_video = root / docs["pointer"]["result_video_relpath"]
    errors.extend(_must_exist(pointer_video, "pointer.result_video_relpath"))

    if errors:
        print("INVALID: viggle handoff contracts", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    print("OK: viggle handoff contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
