#!/usr/bin/env python3
"""
smoke_segment_stitch_runtime.py

PR-34.7g smoke runner:
- builds a temporary job with segment_stitch plan pointer
- runs worker render
- validates segment_stitch_report.v1 artifact
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Smoke test segment stitch runtime execution")
    parser.add_argument(
        "--source-job",
        default="sandbox/jobs/demo-flight-composite.job.json",
        help="Source job path to clone",
    )
    parser.add_argument(
        "--plan",
        default="repo/examples/segment_stitch_plan.v1.example.json",
        help="Segment stitch plan relpath",
    )
    args = parser.parse_args(argv[1:])

    root = _repo_root()
    source_job_path = (root / args.source_job).resolve()
    if not source_job_path.exists():
        print(f"ERROR: source job not found: {source_job_path}", file=sys.stderr)
        return 1

    src = _load(source_job_path)
    job_id = "smoke-segment-stitch-runtime"
    shutil.rmtree(root / "sandbox" / "output" / job_id, ignore_errors=True)
    shutil.rmtree(root / "sandbox" / "logs" / job_id, ignore_errors=True)
    src["job_id"] = job_id
    src.setdefault("render", {})
    src["render"]["output_basename"] = job_id
    src["segment_stitch"] = {
        "plan_relpath": args.plan,
        "enabled": True,
    }

    job_path = root / "sandbox" / "jobs" / f"{job_id}.job.json"
    _write(job_path, src)

    run_worker = [sys.executable, "-m", "repo.worker.render_ffmpeg", "--job", str(job_path)]
    print("RUN:", " ".join(run_worker))
    subprocess.check_call(run_worker, cwd=str(root))

    report_path = root / "sandbox" / "output" / job_id / "segments" / "segment_stitch_report.v1.json"
    if not report_path.exists():
        print(f"ERROR: segment stitch report missing: {report_path}", file=sys.stderr)
        return 1

    validate_cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_segment_stitch_report",
        str(report_path),
    ]
    print("RUN:", " ".join(validate_cmd))
    subprocess.check_call(validate_cmd, cwd=str(root))

    result_path = root / "sandbox" / "output" / job_id / "result.json"
    result = _load(result_path)
    runtime = result.get("segment_stitch_runtime")
    if not isinstance(runtime, dict):
        print("ERROR: result.json missing segment_stitch_runtime", file=sys.stderr)
        return 1

    print("OK:", report_path)
    print("OK:", result_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
