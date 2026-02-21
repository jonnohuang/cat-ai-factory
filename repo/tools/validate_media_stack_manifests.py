#!/usr/bin/env python3
"""
validate_media_stack_manifests.py

Validates Media Stack v1 stage manifests:
- frame_manifest.v1
- audio_manifest.v1
- timeline.v1
- render_manifest.v1
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


def _must_exist(path_s: str, label: str) -> list[str]:
    p = pathlib.Path(path_s)
    if not p.exists():
        return [f"{label} path does not exist: {p}"]
    return []


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Media Stack v1 stage manifests"
    )
    parser.add_argument("--frame", required=True, help="Path to frame_manifest.v1.json")
    parser.add_argument("--audio", required=True, help="Path to audio_manifest.v1.json")
    parser.add_argument("--timeline", required=True, help="Path to timeline.v1.json")
    parser.add_argument(
        "--render", required=True, help="Path to render_manifest.v1.json"
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    schemas = {
        "frame": _load(root / "repo" / "shared" / "frame_manifest.v1.schema.json"),
        "audio": _load(root / "repo" / "shared" / "audio_manifest.v1.schema.json"),
        "timeline": _load(root / "repo" / "shared" / "timeline.v1.schema.json"),
        "render": _load(root / "repo" / "shared" / "render_manifest.v1.schema.json"),
    }
    manifests = {
        "frame": _load(pathlib.Path(args.frame).resolve()),
        "audio": _load(pathlib.Path(args.audio).resolve()),
        "timeline": _load(pathlib.Path(args.timeline).resolve()),
        "render": _load(pathlib.Path(args.render).resolve()),
    }

    errors: list[str] = []
    for key in ("frame", "audio", "timeline", "render"):
        try:
            validate(instance=manifests[key], schema=schemas[key])
        except ValidationError as ex:
            errors.append(f"SCHEMA {key}: {ex.message}")

    job_ids = {str(manifests[k].get("job_id")) for k in manifests}
    if len(job_ids) != 1:
        errors.append(f"job_id mismatch across manifests: {sorted(job_ids)}")

    frame = manifests["frame"]
    if int(frame.get("frame_count", 0)) != len(frame.get("frames", [])):
        errors.append("frame_count must equal len(frames)")
    for path_s in frame.get("frames", []):
        errors.extend(_must_exist(path_s, "frame"))

    audio = manifests["audio"]
    errors.extend(_must_exist(str(audio.get("mix_wav")), "audio.mix_wav"))

    timeline = manifests["timeline"]
    prev_end = 0.0
    for idx, seg in enumerate(timeline.get("segments", [])):
        start = float(seg["start_sec"])
        end = float(seg["end_sec"])
        if end < start:
            errors.append(f"timeline.segments[{idx}] has end_sec < start_sec")
        if start < prev_end:
            errors.append(
                f"timeline.segments[{idx}] starts before previous segment end"
            )
        prev_end = end

    render = manifests["render"]
    errors.extend(_must_exist(str(render.get("final_mp4")), "render.final_mp4"))
    errors.extend(_must_exist(str(render.get("final_srt")), "render.final_srt"))
    errors.extend(_must_exist(str(render.get("result_json")), "render.result_json"))

    if errors:
        print("INVALID: media stack manifests", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1

    print("OK: media stack manifests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
