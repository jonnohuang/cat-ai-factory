#!/usr/bin/env python3
"""
smoke_media_stack.py

PR-33.2 smoke runner:
- runs worker render on a supplied or default job
- validates generated Media Stack v1 stage manifests
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Smoke test Media Stack stage artifacts")
    parser.add_argument(
        "--job",
        default="sandbox/jobs/mochi-dino-replace-smoke-20240515.job.json",
        help="Job JSON path",
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    job_path = (root / args.job).resolve()
    if not job_path.exists():
        print(f"ERROR: job not found: {job_path}", file=sys.stderr)
        return 1

    run_worker = [sys.executable, "-m", "repo.worker.render_ffmpeg", "--job", str(job_path)]
    print("RUN:", " ".join(run_worker))
    subprocess.check_call(run_worker, cwd=str(root))

    job = _load(job_path)
    result_path = root / "sandbox" / "output" / job["job_id"] / "result.json"
    result = _load(result_path)
    media = result.get("media_stack") or {}

    validate_cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_media_stack_manifests",
        "--frame",
        str(media["frame_manifest"]),
        "--audio",
        str(media["audio_manifest"]),
        "--timeline",
        str(media["timeline"]),
        "--render",
        str(media["render_manifest"]),
    ]
    print("RUN:", " ".join(validate_cmd))
    subprocess.check_call(validate_cmd, cwd=str(root))

    print("OK:", result_path)
    print("OK:", media["frame_manifest"])
    print("OK:", media["audio_manifest"])
    print("OK:", media["timeline"])
    print("OK:", media["render_manifest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

