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
    candidate_path = root / "sandbox" / "logs" / "lab" / "promotions" / "smoke-candidate.promotion_candidate.v1.json"
    action_path = root / "sandbox" / "inbox" / "smoke-approve.promotion_action.v1.json"

    candidate = {
        "version": "promotion_candidate.v1",
        "candidate_id": "smoke-candidate",
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
    _write(candidate_path, candidate)

    action = {
        "version": "promotion_action.v1",
        "action_id": "smoke-action-001",
        "candidate_relpath": "sandbox/logs/lab/promotions/smoke-candidate.promotion_candidate.v1.json",
        "decision": "approve",
        "reason": "smoke",
        "submitted_at": "2026-02-18T00:00:00Z"
    }
    _write(action_path, action)

    _run([sys.executable, "-m", "repo.tools.process_promotion_queue"], root)
    _run([sys.executable, "-m", "repo.tools.validate_promotion_registry", "repo/shared/promotion_registry.v1.json"], root)

    registry = _load(root / "repo" / "shared" / "promotion_registry.v1.json")
    approved = registry.get("approved", []) if isinstance(registry, dict) else []
    if not any(isinstance(row, dict) and row.get("candidate_id") == "smoke-candidate" for row in approved):
        print("ERROR: promotion not applied", file=sys.stderr)
        return 1

    print("OK: promotion queue smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
