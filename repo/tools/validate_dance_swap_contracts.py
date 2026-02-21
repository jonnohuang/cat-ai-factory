#!/usr/bin/env python3
"""
validate_dance_swap_contracts.py

Validates Dance Swap v1 contract artifacts:
- dance_swap_loop.v1
- dance_swap_tracks.v1
- optional dance_swap_beatflow.v1

Usage:
  python -m repo.tools.validate_dance_swap_contracts \
    --loop repo/examples/dance_swap_loop.v1.example.json \
    --tracks repo/examples/dance_swap_tracks.v1.example.json \
    --beatflow repo/examples/dance_swap_beatflow.v1.example.json
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


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _is_safe_sandbox_path(p: str) -> bool:
    return p.startswith("sandbox/") and ".." not in p.split("/")


def _validate_loop_semantics(data: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if data["loop_end_frame"] <= data["loop_start_frame"]:
        errs.append("loop_end_frame must be > loop_start_frame")
    if data["fps"] <= 0:
        errs.append("fps must be > 0")
    if not _is_safe_sandbox_path(data["source_video_relpath"]):
        errs.append(
            "source_video_relpath must be sandbox-relative and must not contain '..'"
        )
    return errs


def _validate_tracks_semantics(data: dict[str, Any], hero_ids: set[str]) -> list[str]:
    errs: list[str] = []
    subject_ids: set[str] = set()
    for si, subject in enumerate(data["subjects"]):
        sid = subject["subject_id"]
        hid = subject["hero_id"]
        if sid in subject_ids:
            errs.append(f"subjects[{si}]: duplicate subject_id '{sid}'")
        subject_ids.add(sid)
        if hid not in hero_ids:
            errs.append(f"subjects[{si}]: hero_id '{hid}' not found in hero registry")

        frames = subject["frames"]
        seen_frames: set[int] = set()
        last = -1
        for fi, row in enumerate(frames):
            frame = int(row["frame"])
            if frame in seen_frames:
                errs.append(f"subjects[{si}].frames[{fi}]: duplicate frame '{frame}'")
            seen_frames.add(frame)
            if frame <= last:
                errs.append(
                    f"subjects[{si}].frames[{fi}]: frames must be strictly increasing"
                )
            last = frame
            if not _is_safe_sandbox_path(row["mask_relpath"]):
                errs.append(
                    f"subjects[{si}].frames[{fi}]: mask_relpath must be safe sandbox-relative"
                )
    return errs


def _validate_beatflow_semantics(
    data: dict[str, Any], loop: dict[str, Any] | None
) -> list[str]:
    errs: list[str] = []
    if not _is_safe_sandbox_path(data["source_video_relpath"]):
        errs.append("beatflow.source_video_relpath must be safe sandbox-relative")

    if loop is None:
        return errs

    lo = int(loop["loop_start_frame"])
    hi = int(loop["loop_end_frame"])

    for i, beat in enumerate(data.get("beats", [])):
        bf = int(beat["frame"])
        if not (lo <= bf <= hi):
            errs.append(f"beats[{i}].frame must be within loop bounds [{lo}, {hi}]")
    for i, window in enumerate(data.get("flow_windows", [])):
        s = int(window["start_frame"])
        e = int(window["end_frame"])
        if e <= s:
            errs.append(f"flow_windows[{i}].end_frame must be > start_frame")
        if s < lo or e > hi:
            errs.append(f"flow_windows[{i}] must be within loop bounds [{lo}, {hi}]")
    return errs


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Dance Swap v1 contract artifacts"
    )
    parser.add_argument("--loop", required=True, help="Path to dance_swap_loop.v1 JSON")
    parser.add_argument(
        "--tracks", required=True, help="Path to dance_swap_tracks.v1 JSON"
    )
    parser.add_argument(
        "--beatflow", help="Optional path to dance_swap_beatflow.v1 JSON"
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    loop_schema = _load(root / "repo" / "shared" / "dance_swap_loop.v1.schema.json")
    tracks_schema = _load(root / "repo" / "shared" / "dance_swap_tracks.v1.schema.json")
    beatflow_schema = _load(
        root / "repo" / "shared" / "dance_swap_beatflow.v1.schema.json"
    )
    hero_registry = _load(root / "repo" / "shared" / "hero_registry.v1.json")
    hero_ids = {
        h.get("hero_id")
        for h in hero_registry.get("heroes", [])
        if isinstance(h, dict) and isinstance(h.get("hero_id"), str)
    }

    loop = _load(pathlib.Path(args.loop).resolve())
    tracks = _load(pathlib.Path(args.tracks).resolve())
    beatflow = _load(pathlib.Path(args.beatflow).resolve()) if args.beatflow else None

    errors: list[str] = []

    try:
        validate(instance=loop, schema=loop_schema)
    except ValidationError as ex:
        errors.append(f"SCHEMA loop: {ex.message}")
    try:
        validate(instance=tracks, schema=tracks_schema)
    except ValidationError as ex:
        errors.append(f"SCHEMA tracks: {ex.message}")
    if beatflow is not None:
        try:
            validate(instance=beatflow, schema=beatflow_schema)
        except ValidationError as ex:
            errors.append(f"SCHEMA beatflow: {ex.message}")

    errors.extend(_validate_loop_semantics(loop))
    errors.extend(
        _validate_tracks_semantics(tracks, {x for x in hero_ids if isinstance(x, str)})
    )
    if beatflow is not None:
        errors.extend(_validate_beatflow_semantics(beatflow, loop))

    if errors:
        eprint("INVALID: dance swap contracts")
        for err in errors:
            eprint(f"- {err}")
        return 1

    print("OK: dance swap contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
