#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_events(path: pathlib.Path) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def main(argv: list[str]) -> int:
    root = _repo_root()
    job_id = "smoke-segment-stitch-runtime"
    job_path = root / "sandbox" / "jobs" / f"{job_id}.job.json"
    qc_dir = root / "sandbox" / "logs" / job_id / "qc"
    events_path = root / "sandbox" / "logs" / job_id / "events.ndjson"
    attempts_root = root / "sandbox" / "logs" / job_id / "attempts"
    retry_plan_path = qc_dir / "retry_plan.v1.json"

    env = dict(os.environ)
    py_bin = pathlib.Path(sys.executable).resolve().parent
    env["PATH"] = f"{py_bin}:{env.get('PATH', '')}"

    prep_cmd = [sys.executable, "-m", "repo.tools.smoke_segment_stitch_runtime"]
    print("RUN:", " ".join(prep_cmd))
    subprocess.check_call(prep_cmd, cwd=str(root), env=env)

    quality_report = {
        "version": "recast_quality_report.v1",
        "job_id": job_id,
        "video_relpath": f"sandbox/output/{job_id}/final.mp4",
        "generated_at": "2026-02-17T00:00:00Z",
        "metrics": {
            "identity_consistency": {
                "available": True,
                "score": 0.90,
                "threshold": 0.70,
                "pass": True,
            },
            "mask_edge_bleed": {
                "available": True,
                "score": 0.90,
                "threshold": 0.60,
                "pass": True,
            },
            "temporal_stability": {
                "available": True,
                "score": 0.50,
                "threshold": 0.70,
                "pass": False,
            },
            "loop_seam": {
                "available": True,
                "score": 0.52,
                "threshold": 0.70,
                "pass": False,
            },
            "audio_video": {
                "audio_stream_present": True,
                "av_sync_sec": 0.0,
                "score": 1.0,
                "threshold": 0.95,
                "pass": True,
            },
        },
        "overall": {
            "score": 0.764,
            "pass": False,
            "failed_metrics": ["temporal_stability", "loop_seam"],
        },
    }
    two_pass = {
        "version": "two_pass_orchestration.v1",
        "job_id": job_id,
        "generated_at": "2026-02-17T00:00:00Z",
        "passes": {
            "motion": {"status": "fail", "reason": "smoke-motion-fail"},
            "identity": {"status": "pass"},
        },
    }
    _write_json(qc_dir / "recast_quality_report.v1.json", quality_report)
    _write_json(qc_dir / "two_pass_orchestration.v1.json", two_pass)

    run_cmd = [
        sys.executable,
        "-m",
        "repo.services.orchestrator.ralph_loop",
        "--job",
        str(job_path),
        "--max-retries",
        "1",
    ]
    print("RUN:", " ".join(run_cmd))
    proc = subprocess.run(run_cmd, cwd=str(root), env=env)
    if proc.returncode == 0:
        print(
            "ERROR: expected bounded retry loop to end non-zero under forced motion failures",
            file=sys.stderr,
        )
        return 1

    if not retry_plan_path.exists():
        print(f"ERROR: missing retry plan artifact: {retry_plan_path}", file=sys.stderr)
        return 1
    if not events_path.exists():
        print(f"ERROR: missing events log: {events_path}", file=sys.stderr)
        return 1
    events = _load_events(events_path)
    names = [str(e.get("event", "")) for e in events]
    if "QUALITY_RETRY_EXECUTION" not in names:
        print(
            "ERROR: expected QUALITY_RETRY_EXECUTION event in controller loop",
            file=sys.stderr,
        )
        return 1
    if "QUALITY_RETRY_PLAN" not in names:
        print(
            "ERROR: expected QUALITY_RETRY_PLAN event in controller loop",
            file=sys.stderr,
        )
        return 1
    if "QUALITY_ADVISORY" not in names:
        print(
            "ERROR: expected QUALITY_ADVISORY event in controller loop", file=sys.stderr
        )
        return 1
    if (
        not attempts_root.exists()
        or len([p for p in attempts_root.iterdir() if p.is_dir()]) == 0
    ):
        print("ERROR: expected at least one retry attempt directory", file=sys.stderr)
        return 1

    print("OK:", retry_plan_path)
    print("OK:", events_path)
    print("attempt_dirs:", len([p for p in attempts_root.iterdir() if p.is_dir()]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
