#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    job_id = "smoke-segment-stitch-runtime"
    qc_dir = root / "sandbox" / "logs" / job_id / "qc"

    prep_cmd = [sys.executable, "-m", "repo.tools.smoke_segment_stitch_runtime"]
    print("RUN:", " ".join(prep_cmd))
    subprocess.check_call(prep_cmd, cwd=str(root))

    quality_report = {
        "version": "recast_quality_report.v1",
        "job_id": job_id,
        "video_relpath": f"sandbox/output/{job_id}/final.mp4",
        "generated_at": "2026-02-18T00:00:00Z",
        "metrics": {
            "identity_consistency": {"available": True, "score": 0.9, "threshold": 0.7, "pass": True},
            "mask_edge_bleed": {"available": True, "score": 0.9, "threshold": 0.6, "pass": True},
            "temporal_stability": {"available": True, "score": 0.52, "threshold": 0.7, "pass": False},
            "loop_seam": {"available": True, "score": 0.5, "threshold": 0.7, "pass": False},
            "audio_video": {
                "audio_stream_present": True,
                "av_sync_sec": 0.0,
                "score": 1.0,
                "threshold": 0.95,
                "pass": True,
            },
        },
        "overall": {"score": 0.764, "pass": False, "failed_metrics": ["temporal_stability", "loop_seam"]},
    }
    two_pass = {
        "version": "two_pass_orchestration.v1",
        "job_id": job_id,
        "generated_at": "2026-02-18T00:00:00Z",
        "passes": {"motion": {"status": "fail"}, "identity": {"status": "pass"}},
    }
    _write_json(qc_dir / "recast_quality_report.v1.json", quality_report)
    _write_json(qc_dir / "two_pass_orchestration.v1.json", two_pass)

    steps = [
        [sys.executable, "-m", "repo.tools.validate_qc_policy", "repo/shared/qc_policy.v1.json"],
        [sys.executable, "-m", "repo.tools.run_qc_runner", "--job-id", job_id],
        [sys.executable, "-m", "repo.tools.validate_qc_report", str(qc_dir / "qc_report.v1.json")],
        [sys.executable, "-m", "repo.tools.generate_qc_route_advice", "--job-id", job_id],
        [sys.executable, "-m", "repo.tools.validate_qc_route_advice", str(qc_dir / "qc_route_advice.v1.json")],
    ]
    for cmd in steps:
        print("RUN:", " ".join(cmd))
        subprocess.check_call(cmd, cwd=str(root))

    report = _load(qc_dir / "qc_report.v1.json")
    action = report.get("overall", {}).get("recommended_action")
    if action != "retry_motion":
        print(f"ERROR: expected retry_motion recommendation, got {action!r}", file=sys.stderr)
        return 1

    print("recommended_action:", action)
    print("OK:", qc_dir / "qc_report.v1.json")
    print("OK:", qc_dir / "qc_route_advice.v1.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
