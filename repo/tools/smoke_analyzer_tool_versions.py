#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys


def _load(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"expected object JSON: {path}")
    return data


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[2]
    base = root / "repo" / "canon" / "demo_analyses"
    aid = "smoke-analyzer-core-pack"
    pose = _load(base / f"{aid}.pose_checkpoints.v1.json")
    reverse = _load(base / f"{aid}.caf.video_reverse_prompt.v1.json")
    frame_labels = _load(base / f"{aid}.frame_labels.v1.json")

    required_keys = {"python", "opencv", "mediapipe", "movenet", "librosa", "scenedetect"}
    pose_versions = pose.get("tool_versions")
    reverse_versions = reverse.get("tool_versions")
    frame_versions = frame_labels.get("tool_versions")

    if not isinstance(pose_versions, dict):
        print("ERROR: pose.tool_versions missing", file=sys.stderr)
        return 1
    if set(pose_versions.keys()) != required_keys:
        print(f"ERROR: pose.tool_versions keys mismatch: {sorted(pose_versions.keys())}", file=sys.stderr)
        return 1
    if reverse_versions != pose_versions:
        print("ERROR: reverse.tool_versions mismatch pose.tool_versions", file=sys.stderr)
        return 1
    if frame_versions != pose_versions:
        print("ERROR: frame_labels.tool_versions mismatch pose.tool_versions", file=sys.stderr)
        return 1

    print(f"tool_versions: {pose_versions}")
    print("OK: analyzer tool version stamps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
