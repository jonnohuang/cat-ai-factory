#!/usr/bin/env python3
"""
smoke_recast_quality.py

PR-34.4 smoke runner for deterministic recast quality scoring.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    job_id = "mochi-dino-replace-smoke-20240515"
    cmd = [
        sys.executable,
        "-m",
        "repo.tools.score_recast_quality",
        "--job-id",
        job_id,
        "--video-relpath",
        f"sandbox/output/{job_id}/final.mp4",
        "--hero-image-relpath",
        "sandbox/assets/demo/dance_loop_ref_01.png",
        "--tracks-relpath",
        "repo/examples/dance_swap_tracks.v1.example.json",
        "--subject-id",
        "cat-1",
        "--loop-start-frame",
        "12",
        "--loop-end-frame",
        "348",
    ]
    print("RUN:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(root))
    out = root / "sandbox" / "logs" / job_id / "qc" / "recast_quality_report.v1.json"
    if not out.exists():
        raise SystemExit(f"Missing expected report: {out}")
    print("OK:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
