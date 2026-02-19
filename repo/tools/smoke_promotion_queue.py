#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _write(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load(path: pathlib.Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(cmd: list[str], cwd: pathlib.Path) -> None:
    import subprocess

    proc = subprocess.run(cmd, cwd=str(cwd), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout, end="")
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}")


def main() -> int:
    root = _repo_root()
    smoke_base = root / "sandbox" / "logs" / "lab" / "smoke_promotion_queue"
    queue_path = smoke_base / "promotion_queue.v1.json"
    registry_path = smoke_base / "promotion_registry.v1.json"

    # Clean previous run
    if smoke_base.exists():
        import shutil
        shutil.rmtree(smoke_base)
    smoke_base.mkdir(parents=True, exist_ok=True)

    candidate_good = {
        "candidate_id": "smoke-candidate-good",
        "version": "promotion_candidate.v1",
        "generated_at": "2026-02-18T00:00:00Z",
        "source": {
            "job_id": "smoke-job",
            "summary_relpath": "sandbox/logs/smoke-job/qc/lab_qc_loop_summary.v1.json"
        },
        "proposal": {
            "contract_pointers": {
                "motion_contract": {
                    "relpath": "repo/examples/pose_checkpoints.v1.example.json",
                    "contract_version": "pose_checkpoints.v1"
                }
            },
            "workflow_preset": {
                "workflow_id": "caf_dance_loop_v1",
                "preset_id": "motion_safe_v1"
            },
            "qc_policy_relpath": "repo/shared/qc_policy.v1.json"
        },
        "evidence": {
            "quality_lift": {
                "pass_rate_delta": 0.1,
                "retry_count_delta": -1
            }
        }
    }

    candidate_bad = {
        **candidate_good,
        "candidate_id": "smoke-candidate-bad",
        "evidence": {"quality_lift": {"pass_rate_delta": -0.01, "retry_count_delta": 1}},
    }

    queue_data = {
        "version": "promotion_queue.v1",
        "generated_at": "2026-02-18T00:00:00Z",
        "queue": [candidate_good, candidate_bad]
    }
    _write(queue_path, queue_data)

    # Initial empty registry
    _write(registry_path, {"version": "promotion_registry.v1", "approved": []})

    import subprocess
    cmd = [
        sys.executable,
        "-m",
        "repo.tools.process_promotion_queue",
        "--queue-relpath",
        str(queue_path.resolve().relative_to(root.resolve())).replace("\\", "/"),
        "--registry-relpath",
        str(registry_path.resolve().relative_to(root.resolve())).replace("\\", "/"),
        "--min-pass-rate-delta",
        "0.0",
        "--max-retry-count-delta",
        "0.0",
    ]
    
    proc = subprocess.run(cmd, cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(proc.stdout)
    if proc.returncode != 0:
        print("ERROR: process_promotion_queue failed", file=sys.stderr)
        return 1

    registry = _load(registry_path)
    approved = registry.get("approved", []) if isinstance(registry, dict) else []
    if not isinstance(approved, list):
        print("ERROR: approved list missing", file=sys.stderr)
        return 1
    
    approved_good = [row for row in approved if isinstance(row, dict) and row.get("candidate_id") == "smoke-candidate-good"]
    approved_bad = [row for row in approved if isinstance(row, dict) and row.get("candidate_id") == "smoke-candidate-bad"]

    if len(approved_good) != 1:
        print(f"ERROR: expected exactly one good promotion approval, found {len(approved_good)}", file=sys.stderr)
        return 1
    if approved_bad:
        print("ERROR: bad promotion candidate should not be approved", file=sys.stderr)
        return 1

    # Verify queue is flushed
    queue_after = _load(queue_path)
    queue_rem = queue_after.get("queue", [])
    if queue_rem:
        print(f"ERROR: queue should be empty after processing, found {len(queue_rem)}", file=sys.stderr)
        return 1

    print("OK: promotion queue smoke")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
