#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    root = _repo_root()
    job_id = "smoke-segment-stitch-runtime"
    job_path = root / "sandbox" / "jobs" / f"{job_id}.job.json"
    qc_dir = root / "sandbox" / "logs" / job_id / "qc"
    quality_path = qc_dir / "recast_quality_report.v1.json"
    decision_path = qc_dir / "quality_decision.v1.json"

    pre_cmd = [sys.executable, "-m", "repo.tools.smoke_segment_stitch_runtime"]
    print("RUN:", " ".join(pre_cmd))
    subprocess.check_call(pre_cmd, cwd=str(root))

    original_job_text = job_path.read_text(encoding="utf-8")
    try:
        job = json.loads(original_job_text)
        job["quality_target"] = {"relpath": "repo/examples/quality_target.motion_strict.v1.example.json"}
        _write(job_path, job)

        quality = {
            "version": "recast_quality_report.v1",
            "job_id": job_id,
            "video_relpath": f"sandbox/output/{job_id}/final.mp4",
            "generated_at": "2026-02-17T00:00:00Z",
            "metrics": {
                "identity_consistency": {"available": True, "score": 0.8, "threshold": 0.55, "pass": True},
                "mask_edge_bleed": {"available": True, "score": 0.76, "threshold": 0.45, "pass": True},
                "temporal_stability": {"available": True, "score": 0.82, "threshold": 0.55, "pass": True},
                "loop_seam": {"available": True, "score": 0.85, "threshold": 0.60, "pass": True},
                "audio_video": {
                    "audio_stream_present": True,
                    "av_sync_sec": 0.0,
                    "score": 1.0,
                    "threshold": 0.95,
                    "pass": True
                }
            },
            "overall": {"score": 0.846, "pass": True, "failed_metrics": []}
        }
        _write(quality_path, quality)

        decide_cmd = [sys.executable, "-m", "repo.tools.decide_quality_action", "--job-id", job_id, "--max-retries", "2"]
        print("RUN:", " ".join(decide_cmd))
        subprocess.check_call(decide_cmd, cwd=str(root))

        validate_cmd = [sys.executable, "-m", "repo.tools.validate_quality_decision", str(decision_path)]
        print("RUN:", " ".join(validate_cmd))
        subprocess.check_call(validate_cmd, cwd=str(root))

        decision = _load(decision_path)
        action = decision.get("decision", {}).get("action")
        relpath = decision.get("inputs", {}).get("quality_target_relpath")
        temporal_target = decision.get("policy", {}).get("quality_targets", {}).get("temporal_stability")
        loop_target = decision.get("policy", {}).get("quality_targets", {}).get("loop_seam")
        seg_mode = decision.get("segment_retry", {}).get("mode")

        if relpath != "repo/examples/quality_target.motion_strict.v1.example.json":
            print(f"ERROR: expected quality_target_relpath override, got {relpath!r}", file=sys.stderr)
            return 1
        if temporal_target != 0.9 or loop_target != 0.9:
            print(
                f"ERROR: strict contract thresholds not applied (temporal={temporal_target}, loop={loop_target})",
                file=sys.stderr,
            )
            return 1
        if action != "retry_motion":
            print(f"ERROR: expected retry_motion under strict contract, got {action!r}", file=sys.stderr)
            return 1
        if seg_mode == "none":
            print("ERROR: expected segment retry plan for retry_motion", file=sys.stderr)
            return 1

        print("OK:", decision_path)
        print("quality_target_relpath:", relpath)
        print("decision_action:", action)
        print("segment_retry_mode:", seg_mode)
        return 0
    finally:
        job_path.write_text(original_job_text, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
