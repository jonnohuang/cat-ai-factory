#!/usr/bin/env python3
import json
import os
import pathlib
import shutil
import subprocess
import sys

# Add repo root to sys.path
repo_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(repo_root))

DECIDE_TOOL = repo_root / "repo" / "tools" / "decide_quality_action.py"


def setup_mock_job(job_id, quality_targets_relpath=None):
    job_dir = repo_root / "sandbox" / "jobs"
    job_dir.mkdir(parents=True, exist_ok=True)
    job_path = job_dir / f"{job_id}.job.json"

    if quality_targets_relpath is None:
        # Create a complete quality target for testing in repo/shared (temporary)
        qt_path = repo_root / "repo" / "shared" / f"tmp_qt_{job_id}.v1.json"
        with open(qt_path, "w") as f:
            json.dump(
                {
                    "version": "quality_target.v1",
                    "thresholds": {
                        "identity_consistency": 0.7,
                        "mask_edge_bleed": 0.6,
                        "temporal_stability": 0.7,
                        "loop_seam": 0.7,
                        "audio_video": 0.95,
                        "background_stability": 0.8,
                        "identity_drift": 0.8,
                    },
                },
                f,
                indent=2,
            )
        quality_targets_relpath = f"repo/shared/tmp_qt_{job_id}.v1.json"

    job_data = {
        "version": "job.v1",
        "job_id": job_id,
        "quality_target": {"relpath": quality_targets_relpath},
        "pointer_resolution": {
            "version": "pointer_resolution.v1",
            "selected": {"quality_target": {"relpath": quality_targets_relpath}},
            "required": ["quality_target"],
        },
    }

    with open(job_path, "w") as f:
        json.dump(job_data, f, indent=2)
    return job_path


def setup_mock_report(job_id, gates=None, recommended_action="retry_motion"):
    qc_dir = repo_root / "sandbox" / "logs" / job_id / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    report_path = qc_dir / "qc_report.v1.json"

    report_data = {
        "version": "qc_report.v1",
        "overall": {"pass": False, "recommended_action": recommended_action},
        "gates": gates or [],
    }

    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2)
    return report_path


def run_decide(job_id, max_retries=2):
    cmd = [
        sys.executable,
        str(DECIDE_TOOL),
        "--job-id",
        job_id,
        "--max-retries",
        str(max_retries),
    ]
    env = os.environ.copy()
    env["CAF_QC_DEBUG"] = "1"
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    decision_path = (
        repo_root / "sandbox" / "logs" / job_id / "qc" / "quality_decision.v1.json"
    )
    if not decision_path.exists():
        return (
            None,
            f"Decision file missing. STDOUT: {result.stdout}, STDERR: {result.stderr}",
        )

    with open(decision_path, "r") as f:
        return json.load(f), result.stdout + "\n" + result.stderr


def test_strict_routing():
    print("Testing Strict Routing Authority...")

    # CASE 1: Unknown Gate with Full Coverage -> Retry Motion
    job_id = "smoke-qc-unknown"
    setup_mock_job(job_id)
    # Provide all mandatory metrics but make one 'unknown'
    gates = [
        {
            "metric": m,
            "dimension": (
                "motion"
                if m in ["temporal_stability", "loop_seam", "background_stability"]
                else "identity"
            ),
            "status": "pass",
        }
        for m in [
            "identity_consistency",
            "mask_edge_bleed",
            "temporal_stability",
            "loop_seam",
            "audio_video",
            "background_stability",
            "identity_drift",
        ]
    ]
    # Set one to unknown
    gates[2]["status"] = "unknown"  # temporal_stability
    setup_mock_report(job_id, gates=gates)
    payload, err = run_decide(job_id)
    decision = payload["decision"]
    if decision["action"] != "retry_motion":
        print(f"DEBUG: reason={decision['reason']}")
        print(f"DEBUG: stdout/err={err}")
    assert (
        decision["action"] == "retry_motion"
    ), f"Expected retry_motion due to unknown gate, got {decision['action']}"
    print("  [PASS] CASE 1: Unknown gate treated as failure.")

    # CASE 2: Missing Mandatory Metric -> HITL Escalation
    job_id = "smoke-qc-missing-metric"
    setup_mock_job(job_id)
    setup_mock_report(
        job_id,
        gates=[
            {"metric": "temporal_stability", "dimension": "motion", "status": "pass"}
            # missing identity_consistency which is in DEFAULT_QUALITY_TARGETS
        ],
    )
    payload, err = run_decide(job_id)
    decision = payload["decision"]
    assert (
        decision["action"] == "escalate_hitl"
    ), f"Expected escalate_hitl due to missing metric, got {decision['action']}"
    assert (
        "missing mandatory metrics" in decision["reason"]
    ), f"Expected reason to mention missing metrics, got {decision['reason']}"
    print("  [PASS] CASE 2: Missing mandatory metric caused HITL escalation.")

    # CASE 3: Budget Lock -> HITL Escalation
    job_id = "smoke-qc-budget"
    setup_mock_job(job_id)
    # Provide all mandatory metrics
    gates = [
        {
            "metric": m,
            "dimension": (
                "motion"
                if m in ["temporal_stability", "loop_seam", "background_stability"]
                else "identity"
            ),
            "status": "pass",
        }
        for m in [
            "identity_consistency",
            "mask_edge_bleed",
            "temporal_stability",
            "loop_seam",
            "audio_video",
            "background_stability",
            "identity_drift",
        ]
    ]
    setup_mock_report(job_id, gates=gates, recommended_action="retry_motion")

    # Create fake attempts to simulate being at attempt 2
    attempts_dir = repo_root / "sandbox" / "logs" / job_id / "attempts"
    (attempts_dir / "run-0001").mkdir(parents=True, exist_ok=True)
    (attempts_dir / "run-0002").mkdir(parents=True, exist_ok=True)

    # If max_retries is 2, and we've done 2, the next would be 3 (exceeds budget)
    payload, err = run_decide(job_id, max_retries=2)
    decision = payload["decision"]
    if decision["action"] != "escalate_hitl":
        print(f"DEBUG: reason={decision['reason']}")
        print(f"DEBUG: stdout/err={err}")
    assert (
        decision["action"] == "escalate_hitl"
    ), f"Expected escalate_hitl due to budget limit, got {decision['action']}"
    assert (
        "budget exceeded" in decision["reason"]
    ), f"Expected reason to mention budget, got {decision['reason']}"
    print("  [PASS] CASE 3: Budget lock enforced.")

    print("Strict Routing smoke test PASSED!")


if __name__ == "__main__":
    try:
        test_strict_routing()
    except Exception as e:
        print(f"Smoke test FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        for jid in ["smoke-qc-unknown", "smoke-qc-missing-metric", "smoke-qc-budget"]:
            job_path = repo_root / "sandbox" / "jobs" / f"{jid}.job.json"
            if job_path.exists():
                job_path.unlink()
            logs_dir = repo_root / "sandbox" / "logs" / jid
            if logs_dir.exists():
                shutil.rmtree(logs_dir)
            # Cleanup tmp qt files
            qt_path = repo_root / "repo" / "shared" / f"tmp_qt_{jid}.v1.json"
            if qt_path.exists():
                qt_path.unlink()
