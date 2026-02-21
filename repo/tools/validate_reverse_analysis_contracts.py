#!/usr/bin/env python3
"""
validate_reverse_analysis_contracts.py

Validate PR-34.7a reverse-analysis contracts:
- caf.video_reverse_prompt.v1
- beat_grid.v1
- pose_checkpoints.v1
- keyframe_checkpoints.v1

Usage:
  python repo/tools/validate_reverse_analysis_contracts.py \
    --reverse repo/examples/caf.video_reverse_prompt.v1.example.json \
    --beat repo/examples/beat_grid.v1.example.json \
    --pose repo/examples/pose_checkpoints.v1.example.json \
    --keyframes repo/examples/keyframe_checkpoints.v1.example.json
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


def _validate_monotonic_secs(values: list[float], label: str) -> list[str]:
    errs: list[str] = []
    last = -1.0
    for i, cur in enumerate(values):
        if cur < last:
            errs.append(f"{label}[{i}] must be monotonic non-decreasing")
        last = cur
    return errs


def _validate_semantics(
    reverse_doc: dict[str, Any],
    beat_doc: dict[str, Any],
    pose_doc: dict[str, Any],
    keyframe_doc: dict[str, Any],
) -> list[str]:
    errs: list[str] = []

    analysis_ids = {
        reverse_doc.get("analysis_id"),
        beat_doc.get("analysis_id"),
        pose_doc.get("analysis_id"),
        keyframe_doc.get("analysis_id"),
    }
    if len(analysis_ids) != 1:
        errs.append("analysis_id must match across reverse/beat/pose/keyframes")

    src_paths = {
        reverse_doc.get("source_video_relpath"),
        beat_doc.get("source_video_relpath"),
        pose_doc.get("source_video_relpath"),
        keyframe_doc.get("source_video_relpath"),
    }
    if len(src_paths) != 1:
        errs.append(
            "source_video_relpath must match across reverse/beat/pose/keyframes"
        )

    reverse_tools = reverse_doc.get("tool_versions")
    pose_tools = pose_doc.get("tool_versions")
    if isinstance(reverse_tools, dict) and isinstance(pose_tools, dict):
        if reverse_tools != pose_tools:
            errs.append("tool_versions mismatch between reverse and pose contracts")
    else:
        errs.append("tool_versions missing in reverse and/or pose contracts")

    shots = reverse_doc.get("truth", {}).get("shots", [])
    visual_facts = reverse_doc.get("truth", {}).get("visual_facts", {})
    shot_starts: list[float] = []
    for i, shot in enumerate(shots):
        start = float(shot.get("start_sec", 0.0))
        end = float(shot.get("end_sec", 0.0))
        shot_starts.append(start)
        if end <= start:
            errs.append(f"truth.shots[{i}].end_sec must be > start_sec")

        camera = shot.get("camera")
        if isinstance(camera, str) and camera == "unknown":
            if (
                "camera_confidence" in shot
                and float(shot.get("camera_confidence", 0.0)) > 0.0
            ):
                errs.append(
                    f"truth.shots[{i}].camera=unknown must not have positive camera_confidence"
                )

        luma = shot.get("brightness_luma_mean")
        if luma is not None and not (0.0 <= float(luma) <= 255.0):
            errs.append(f"truth.shots[{i}].brightness_luma_mean must be in [0,255]")

        ph = shot.get("palette_hint")
        if ph is not None and not (
            isinstance(ph, str) and ph.startswith("#") and len(ph) == 7
        ):
            errs.append(f"truth.shots[{i}].palette_hint must be #RRGGBB")

    if isinstance(visual_facts, dict):
        mode = visual_facts.get("camera_movement_mode")
        conf = visual_facts.get("camera_movement_confidence")
        luma_mean = visual_facts.get("luma_mean")
        palette = visual_facts.get("palette_top_hex", [])
        if mode == "unknown" and isinstance(conf, (int, float)) and float(conf) > 0:
            errs.append(
                "truth.visual_facts.camera_movement_mode=unknown requires camera_movement_confidence=0"
            )
        if luma_mean is not None and not (0.0 <= float(luma_mean) <= 255.0):
            errs.append("truth.visual_facts.luma_mean must be in [0,255] when present")
        if isinstance(palette, list):
            for i, item in enumerate(palette):
                if not (
                    isinstance(item, str) and item.startswith("#") and len(item) == 7
                ):
                    errs.append(
                        f"truth.visual_facts.palette_top_hex[{i}] must be #RRGGBB"
                    )
        if isinstance(mode, str) and mode != "unknown":
            for i, shot in enumerate(shots):
                if not isinstance(shot, dict):
                    continue
                shot_mode = shot.get("camera")
                if isinstance(shot_mode, str) and shot_mode not in (mode, "unknown"):
                    errs.append(
                        f"truth.shots[{i}].camera must align with truth.visual_facts.camera_movement_mode"
                    )
    errs.extend(_validate_monotonic_secs(shot_starts, "truth.shots.start_sec"))

    beat_times = [float(x.get("t_sec", 0.0)) for x in beat_doc.get("beats", [])]
    errs.extend(_validate_monotonic_secs(beat_times, "beats.t_sec"))

    pose_times = [float(x.get("t_sec", 0.0)) for x in pose_doc.get("checkpoints", [])]
    errs.extend(_validate_monotonic_secs(pose_times, "pose.checkpoints.t_sec"))

    keyframe_times = [
        float(x.get("t_sec", 0.0)) for x in keyframe_doc.get("keyframes", [])
    ]
    errs.extend(_validate_monotonic_secs(keyframe_times, "keyframes.t_sec"))

    vendor_sources = reverse_doc.get("suggestions", {}).get("vendor_sources", [])
    for i, source in enumerate(vendor_sources):
        relpath = str(source.get("relpath", ""))
        if not relpath.startswith("repo/analysis/vendor/"):
            errs.append(
                f"suggestions.vendor_sources[{i}].relpath must stay under repo/analysis/vendor/"
            )

    measured_truth = float(reverse_doc.get("confidence", {}).get("measured_truth", 0.0))
    inferred = float(reverse_doc.get("confidence", {}).get("inferred_semantics", 0.0))
    if measured_truth < inferred:
        errs.append(
            "confidence.measured_truth should be >= confidence.inferred_semantics for truth-first posture"
        )

    return errs


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate reverse-analysis contracts")
    parser.add_argument(
        "--reverse", required=True, help="Path to caf.video_reverse_prompt.v1 JSON"
    )
    parser.add_argument("--beat", required=True, help="Path to beat_grid.v1 JSON")
    parser.add_argument(
        "--pose", required=True, help="Path to pose_checkpoints.v1 JSON"
    )
    parser.add_argument(
        "--keyframes", required=True, help="Path to keyframe_checkpoints.v1 JSON"
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()

    docs = {
        "reverse": _load(pathlib.Path(args.reverse).resolve()),
        "beat": _load(pathlib.Path(args.beat).resolve()),
        "pose": _load(pathlib.Path(args.pose).resolve()),
        "keyframes": _load(pathlib.Path(args.keyframes).resolve()),
    }
    schemas = {
        "reverse": _load(
            root / "repo" / "shared" / "caf.video_reverse_prompt.v1.schema.json"
        ),
        "beat": _load(root / "repo" / "shared" / "beat_grid.v1.schema.json"),
        "pose": _load(root / "repo" / "shared" / "pose_checkpoints.v1.schema.json"),
        "keyframes": _load(
            root / "repo" / "shared" / "keyframe_checkpoints.v1.schema.json"
        ),
    }

    errors: list[str] = []
    for key in ("reverse", "beat", "pose", "keyframes"):
        try:
            validate(instance=docs[key], schema=schemas[key])
        except ValidationError as ex:
            errors.append(f"SCHEMA {key}: {ex.message}")

    if not errors:
        errors.extend(
            _validate_semantics(
                docs["reverse"], docs["beat"], docs["pose"], docs["keyframes"]
            )
        )

    if errors:
        eprint("INVALID: reverse-analysis contracts")
        for err in errors:
            eprint(f"- {err}")
        return 1

    print("OK: reverse-analysis contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
