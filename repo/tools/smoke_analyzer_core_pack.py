#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import sys


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    print(proc.stdout, end="")
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[2]
    input_video = root / "sandbox" / "assets" / "demo" / "mochi_dance_loop_swap.mp4"
    if not input_video.exists():
        print(f"ERROR: sample video not found: {input_video}", file=sys.stderr)
        return 1

    analysis_id = "smoke-analyzer-core-pack"
    out_dir = root / "repo" / "canon" / "demo_analyses"

    _run(
        [
            sys.executable,
            "-m",
            "repo.tools.build_analyzer_core_pack",
            "--input",
            str(input_video),
            "--analysis-id",
            analysis_id,
            "--out-dir",
            "repo/canon/demo_analyses",
            "--overwrite",
        ]
    )

    reverse = out_dir / f"{analysis_id}.caf.video_reverse_prompt.v1.json"
    frame_labels = out_dir / f"{analysis_id}.frame_labels.v1.json"
    beat = out_dir / f"{analysis_id}.beat_grid.v1.json"
    pose = out_dir / f"{analysis_id}.pose_checkpoints.v1.json"
    keyframes = out_dir / f"{analysis_id}.keyframe_checkpoints.v1.json"
    seg_plan = out_dir / f"{analysis_id}.segment_stitch_plan.v1.json"

    _run(
        [
            sys.executable,
            "-m",
            "repo.tools.validate_reverse_analysis_contracts",
            "--reverse",
            str(reverse),
            "--beat",
            str(beat),
            "--pose",
            str(pose),
            "--keyframes",
            str(keyframes),
        ]
    )
    _run(
        [
            sys.executable,
            "-m",
            "repo.tools.validate_frame_labels",
            "--frame-labels",
            str(frame_labels),
            "--reverse",
            str(reverse),
            "--keyframes",
            str(keyframes),
        ]
    )
    _run(
        [sys.executable, "-m", "repo.tools.validate_segment_stitch_plan", str(seg_plan)]
    )
    _run([sys.executable, "-m", "repo.tools.smoke_analyzer_tool_versions"])

    print("OK: analyzer core pack smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
