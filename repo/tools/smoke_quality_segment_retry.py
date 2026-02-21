#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    root = _repo_root()
    job_id = "smoke-segment-stitch-runtime"
    qc_dir = root / "sandbox" / "logs" / job_id / "qc"
    quality_path = qc_dir / "recast_quality_report.v1.json"
    decision_path = qc_dir / "quality_decision.v1.json"
    two_pass_path = qc_dir / "two_pass_orchestration.v1.json"

    shutil.rmtree(root / "sandbox" / "output" / job_id, ignore_errors=True)
    shutil.rmtree(root / "sandbox" / "logs" / job_id, ignore_errors=True)

    pre_cmd = [sys.executable, "-m", "repo.tools.smoke_segment_stitch_runtime"]
    print("RUN:", " ".join(pre_cmd))
    subprocess.check_call(pre_cmd, cwd=str(root))

    quality = {
        "version": "recast_quality_report.v1",
        "job_id": job_id,
        "video_relpath": f"sandbox/output/{job_id}/final.mp4",
        "generated_at": "2026-02-17T00:00:00Z",
        "metrics": {
            "identity_consistency": {
                "available": True,
                "score": 0.85,
                "threshold": 0.55,
                "pass": True,
            },
            "mask_edge_bleed": {
                "available": True,
                "score": 0.78,
                "threshold": 0.45,
                "pass": True,
            },
            "temporal_stability": {
                "available": True,
                "score": 0.66,
                "threshold": 0.55,
                "pass": True,
            },
            "loop_seam": {
                "available": True,
                "score": 0.67,
                "threshold": 0.60,
                "pass": True,
            },
            "audio_video": {
                "audio_stream_present": True,
                "av_sync_sec": 0.0,
                "score": 1.0,
                "threshold": 0.95,
                "pass": True,
            },
        },
        "overall": {"score": 0.792, "pass": True, "failed_metrics": []},
    }
    _write_json(quality_path, quality)
    two_pass = {
        "version": "two_pass_orchestration.v1",
        "job_id": job_id,
        "generated_at": "2026-02-17T00:00:00Z",
        "passes": {
            "motion": {"status": "fail", "reason": "smoke-motion-fail"},
            "identity": {"status": "pass"},
        },
    }
    _write_json(two_pass_path, two_pass)

    decide_cmd = [
        sys.executable,
        "-m",
        "repo.tools.decide_quality_action",
        "--job-id",
        job_id,
        "--max-retries",
        "2",
    ]
    print("RUN:", " ".join(decide_cmd))
    subprocess.check_call(decide_cmd, cwd=str(root))

    validate_cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_quality_decision",
        str(decision_path),
    ]
    print("RUN:", " ".join(validate_cmd))
    subprocess.check_call(validate_cmd, cwd=str(root))

    decision = _load(decision_path)
    action = decision.get("decision", {}).get("action")
    seg_retry = decision.get("segment_retry", {})
    mode = seg_retry.get("mode")
    targets = seg_retry.get("target_segments", [])
    trigger_metrics = seg_retry.get("trigger_metrics", [])

    if action != "retry_motion":
        print(f"ERROR: expected retry_motion, got {action!r}", file=sys.stderr)
        return 1
    if mode not in {"retry_all", "retry_selected"}:
        print(f"ERROR: expected segment retry mode, got {mode!r}", file=sys.stderr)
        return 1
    if mode == "retry_selected" and not targets:
        print("ERROR: retry_selected requires target segments", file=sys.stderr)
        return 1
    if (
        "temporal_stability" not in trigger_metrics
        and "loop_seam" not in trigger_metrics
    ):
        print(
            "ERROR: expected motion trigger metrics in segment retry plan",
            file=sys.stderr,
        )
        return 1

    print("OK:", decision_path)
    print("decision_action:", action)
    print("segment_retry_mode:", mode)
    print("segment_retry_targets:", targets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
