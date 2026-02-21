#!/usr/bin/env python3
import json
import pathlib
import shutil
import sys


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def _write(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def main():
    root = _repo_root()
    sandbox = root / "sandbox" / "logs" / "smoke_qc_unknown_metrics"
    if sandbox.exists():
        shutil.rmtree(sandbox)
    sandbox.mkdir(parents=True, exist_ok=True)

    qc_dir = sandbox / "qc"
    qc_dir.mkdir(parents=True)

    # 1. Job
    job_path = root / "sandbox" / "jobs" / "smoke_qc_unknown_metrics.job.json"
    _write(
        job_path,
        {
            "job_id": "smoke_qc_unknown_metrics",
            "quality_target": {"relpath": "repo/shared/quality_target.v1.json"},
        },
    )

    # 2. Policy with a gate that expects a metric which will be missing
    policy_path = sandbox / "qc_policy_fail_loud.v1.json"
    _write(
        policy_path,
        {
            "version": "qc_policy.v1",
            "gates": [
                {
                    "gate_id": "smoke_missing_metric_gate",
                    "metric": "non_existent_metric_xyz",
                    "threshold": 0.5,
                    "failure_action": "escalate_hitl",
                }
            ],
            "routing": {
                "failure_action_priority": ["escalate_hitl"],
                "fallback_action": "escalate_hitl",
            },
        },
    )

    # 3. Quality report missing that metric
    quality_path = qc_dir / "recast_quality_report.v1.json"
    _write(
        quality_path,
        {
            "version": "recast_quality_report.v1",
            "metrics": {"some_other_metric": {"score": 0.9}},
        },
    )

    # 4. Run run_qc_runner
    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "repo.tools.run_qc_runner",
        "--job-id",
        "smoke_qc_unknown_metrics",
        "--qc-policy-relpath",
        str(policy_path.relative_to(root)),
    ]

    proc = subprocess.run(
        cmd, cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print("ERROR: run_qc_runner failed unexpectedly")
        return 1

    # 5. Verify qc_report.v1.json outcome
    report_path = qc_dir / "qc_report.v1.json"
    if not report_path.exists():
        print("ERROR: qc_report.v1.json not generated")
        return 1

    report = json.loads(report_path.read_text())
    overall = report.get("overall", {})
    gates = report.get("gates", [])

    # Expect: fail because metric was missing (status: unknown treated as fail)
    if overall.get("pass") is True:
        print("ERROR: Report passed despite missing metric!")
        return 1

    gate = next((g for g in gates if g["gate_id"] == "smoke_missing_metric_gate"), None)
    if not gate:
        print("ERROR: Gate missing from report")
        return 1

    if gate["status"] != "unknown":
        print(f"ERROR: Expected gate status 'unknown', got '{gate['status']}'")
        return 1

    if overall["recommended_action"] != "escalate_hitl":
        print(f"ERROR: Expected 'escalate_hitl', got '{overall['recommended_action']}'")
        return 1

    print("OK: Unknown metric correctly caused fail-closed (escalate_hitl)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
