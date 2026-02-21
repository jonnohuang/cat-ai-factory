#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from typing import Any, Dict


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _load(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"expected object: {path}")
    return data


def _save(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run(cmd: list[str], cwd: pathlib.Path, env: Dict[str, str] | None = None) -> None:
    print("RUN:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def main(argv: list[str]) -> int:
    root = _repo_root()
    job_id = "smoke-segment-stitch-runtime"
    job_path = root / "sandbox" / "jobs" / f"{job_id}.job.json"
    decision_path = (
        root / "sandbox" / "logs" / job_id / "qc" / "quality_decision.v1.json"
    )
    _run([sys.executable, "-m", "repo.tools.smoke_qc_policy_report_contract"], root)

    original = _load(job_path)
    mutated = dict(original)
    mutated["quality_policy"] = {
        "relpath": "repo/examples/qc_policy.authority_trial.v1.example.json"
    }
    _save(job_path, mutated)
    try:
        env = dict(os.environ)
        env["CAF_QC_AUTHORITY_TRIAL"] = "1"
        _run(
            [
                sys.executable,
                "-m",
                "repo.tools.decide_quality_action",
                "--job-id",
                job_id,
                "--max-retries",
                "2",
            ],
            root,
            env,
        )
        decision = _load(decision_path)
        policy = decision.get("policy", {})
        if not isinstance(policy, dict):
            raise RuntimeError("missing policy block")
        if policy.get("authority_trial_enabled") is not True:
            raise RuntimeError("expected authority_trial_enabled=true")
        if policy.get("authority_trial_rollback") is not True:
            raise RuntimeError("expected authority_trial_rollback=true")
    finally:
        _save(job_path, original)
    print("OK: qc authority trial smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
