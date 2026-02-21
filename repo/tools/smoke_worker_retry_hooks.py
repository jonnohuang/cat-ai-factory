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


def _load(path: pathlib.Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str]) -> int:
    root = _repo_root()
    job_id = "smoke-segment-stitch-runtime"
    job_path = root / "sandbox" / "jobs" / f"{job_id}.job.json"
    qc_dir = root / "sandbox" / "logs" / job_id / "qc"
    retry_plan_path = qc_dir / "retry_plan.v1.json"
    report_path = (
        root
        / "sandbox"
        / "output"
        / job_id
        / "segments"
        / "segment_stitch_report.v1.json"
    )
    result_path = root / "sandbox" / "output" / job_id / "result.json"

    prep_cmd = [sys.executable, "-m", "repo.tools.smoke_segment_stitch_runtime"]
    print("RUN:", " ".join(prep_cmd))
    subprocess.check_call(prep_cmd, cwd=str(root))

    retry_plan = {
        "version": "retry_plan.v1",
        "job_id": job_id,
        "generated_at": "2026-02-17T00:00:00Z",
        "source": {
            "quality_decision_relpath": f"sandbox/logs/{job_id}/qc/quality_decision.v1.json",
            "action": "retry_motion",
            "reason": "smoke worker retry hooks",
        },
        "retry": {
            "enabled": True,
            "retry_type": "motion",
            "next_attempt": 1,
            "max_retries": 2,
            "segment_retry": {
                "mode": "retry_selected",
                "target_segments": ["seg_002"],
                "trigger_metrics": ["temporal_stability", "loop_seam"],
            },
            "provider_switch": {
                "mode": "video_provider",
                "current_provider": "vertex_veo",
                "next_provider": "wan_local",
                "provider_order_index": 1,
            },
            "pass_target": "motion",
        },
        "state": {
            "motion_status": "fail",
            "identity_status": "pass",
            "terminal_state": "none",
        },
    }
    _write_json(retry_plan_path, retry_plan)

    env = dict(os.environ)
    env["CAF_RETRY_PLAN_PATH"] = str(retry_plan_path.resolve())
    env["CAF_RETRY_ATTEMPT_ID"] = "run-0002"
    run_worker = [
        sys.executable,
        "-m",
        "repo.worker.render_ffmpeg",
        "--job",
        str(job_path),
    ]
    print("RUN:", " ".join(run_worker))
    subprocess.check_call(run_worker, cwd=str(root), env=env)

    validate_cmd = [
        sys.executable,
        "-m",
        "repo.tools.validate_segment_stitch_report",
        str(report_path),
    ]
    print("RUN:", " ".join(validate_cmd))
    subprocess.check_call(validate_cmd, cwd=str(root))

    report = _load(report_path)
    hook = report.get("retry_hook_applied")
    if not isinstance(hook, dict):
        print(
            "ERROR: segment stitch report missing retry_hook_applied", file=sys.stderr
        )
        return 1
    if hook.get("retry_type") != "motion":
        print(
            f"ERROR: expected retry_type=motion, got {hook.get('retry_type')!r}",
            file=sys.stderr,
        )
        return 1
    seg_ids = [
        str(s.get("segment_id"))
        for s in report.get("segments", [])
        if isinstance(s, dict)
    ]
    if seg_ids != ["seg_002"]:
        print(
            f"ERROR: expected only seg_002 after retry-selected hook, got {seg_ids!r}",
            file=sys.stderr,
        )
        return 1

    result = _load(result_path)
    if not isinstance(result.get("worker_retry_hook"), dict):
        print("ERROR: result.json missing worker_retry_hook", file=sys.stderr)
        return 1

    print("OK:", report_path)
    print("retry_segments:", seg_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
