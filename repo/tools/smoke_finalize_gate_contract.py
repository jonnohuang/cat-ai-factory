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


def _decide(root: pathlib.Path, job_id: str, max_retries: int = 2) -> None:
    cmd = [
        sys.executable,
        "-m",
        "repo.tools.decide_quality_action",
        "--job-id",
        job_id,
        "--max-retries",
        str(max_retries),
    ]
    print("RUN:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(root))


def _validate(root: pathlib.Path, path: pathlib.Path) -> None:
    cmd = [sys.executable, "-m", "repo.tools.validate_finalize_gate", str(path)]
    print("RUN:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(root))


def main(argv: list[str]) -> int:
    _ = argv
    root = _repo_root()
    job_id = "smoke-segment-stitch-runtime"
    output_dir = root / "sandbox" / "output" / job_id
    logs_dir = root / "sandbox" / "logs" / job_id
    qc_dir = logs_dir / "qc"
    gate_path = qc_dir / "finalize_gate.v1.json"
    decision_path = qc_dir / "quality_decision.v1.json"

    shutil.rmtree(output_dir, ignore_errors=True)
    shutil.rmtree(logs_dir, ignore_errors=True)

    pre_cmd = [sys.executable, "-m", "repo.tools.smoke_segment_stitch_runtime"]
    print("RUN:", " ".join(pre_cmd))
    subprocess.check_call(pre_cmd, cwd=str(root))

    baseline_quality = {
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
    baseline_two_pass = {
        "version": "two_pass_orchestration.v1",
        "job_id": job_id,
        "generated_at": "2026-02-17T00:00:00Z",
        "passes": {
            "motion": {"status": "pass"},
            "identity": {"status": "pass"},
        },
    }
    _write_json(qc_dir / "recast_quality_report.v1.json", baseline_quality)
    _write_json(qc_dir / "two_pass_orchestration.v1.json", baseline_two_pass)

    _decide(root, job_id)
    _validate(root, gate_path)
    first_gate = _load(gate_path)
    first_action = _load(decision_path).get("decision", {}).get("action")
    first_allow = bool(first_gate.get("gate", {}).get("allow_finalize") is True)
    if first_allow != (first_action == "proceed_finalize"):
        print("ERROR: finalize gate/action mismatch in baseline run", file=sys.stderr)
        return 1

    fail_two_pass = {
        "version": "two_pass_orchestration.v1",
        "job_id": job_id,
        "generated_at": "2026-02-17T00:00:00Z",
        "passes": {
            "motion": {"status": "fail", "reason": "smoke-motion-fail"},
            "identity": {"status": "pass"},
        },
    }
    _write_json(qc_dir / "two_pass_orchestration.v1.json", fail_two_pass)
    _decide(root, job_id)
    _validate(root, gate_path)
    block_gate = _load(gate_path)
    action = _load(decision_path).get("decision", {}).get("action")
    if block_gate.get("gate", {}).get("allow_finalize") is not False:
        print(
            "ERROR: expected allow_finalize=False for retry/fail quality",
            file=sys.stderr,
        )
        return 1
    if action == "proceed_finalize":
        print(
            "ERROR: expected non-finalize action in failing scenario", file=sys.stderr
        )
        return 1

    print("OK:", gate_path)
    print("baseline_allow_finalize:", first_gate.get("gate", {}).get("allow_finalize"))
    print("baseline_action:", first_action)
    print("block_allow_finalize:", block_gate.get("gate", {}).get("allow_finalize"))
    print("block_action:", action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
