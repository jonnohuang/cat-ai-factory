#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SANDBOX = REPO_ROOT / "sandbox"
LOGS = SANDBOX / "logs"
JOBS = SANDBOX / "jobs"

def setup_mock_job(job_id, require_costume=False):
    job = {
        "job_id": job_id,
        "render": {
            "output_basename": job_id
        }
    }
    if require_costume:
        job["continuity_pack"] = {
            "relpath": "repo/shared/smoke_continuity_pack.v1.json"
        }
        # Create the mock pack
        pack = {
            "version": "episode_continuity_pack.v1",
            "rules": {
                "require_costume_fidelity": True
            }
        }
        (REPO_ROOT / "repo/shared/smoke_continuity_pack.v1.json").write_text(json.dumps(pack, indent=2))

    job_path = JOBS / f"{job_id}.job.json"
    job_path.parent.mkdir(parents=True, exist_ok=True)
    job_path.write_text(json.dumps(job, indent=2))
    return job_path

def setup_mock_qc_data(job_id, metrics):
    qc_dir = LOGS / job_id / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    quality_report = {
        "version": "recast_quality_report.v1",
        "metrics": metrics
    }
    (qc_dir / "recast_quality_report.v1.json").write_text(json.dumps(quality_report, indent=2))

def setup_mock_costume_data(job_id, passed):
    qc_dir = LOGS / job_id / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "version": "costume_fidelity.v1",
        "pass": passed
    }
    (qc_dir / "costume_fidelity.v1.json").write_text(json.dumps(report, indent=2))

def run_smoke_scenario(name, metrics, costume_pass=True, require_costume=False):
    print(f"\n--- Scenario: {name} ---")
    job_id = f"smoke-{name}"
    setup_mock_job(job_id, require_costume=require_costume)
    setup_mock_qc_data(job_id, metrics)
    if "costume_fidelity" in metrics or costume_pass is False:
         setup_mock_costume_data(job_id, costume_pass)

    # 1. Run QC Runner
    print(f"Running QC runner for {job_id}...")
    subprocess.run([
        sys.executable,
        "repo/tools/run_qc_runner.py",
        "--job-id", job_id
    ], check=True, capture_output=True)

    qc_report_path = LOGS / job_id / "qc" / "qc_report.v1.json"
    qc_report = json.loads(qc_report_path.read_text())
    recommended = qc_report["overall"]["recommended_action"]
    print(f"QC Recommended Action: {recommended}")

    # 2. Run pseudo-Supervisor decision (via tool or manual check of the ralph_loop logic)
    # Since production_supervisor_decide is internal to ralph_loop, we verify it by running a test script
    # that imports it or just checks the logic we refactored.

    # For now, let's verify the QC report contents
    for gate in qc_report["gates"]:
        if gate["status"] in ("HARD_FAIL", "SOFT_FAIL"):
            print(f"  [FAIL] {gate['gate_id']} ({gate['metric']}): status={gate['status']}, severity={gate['severity']}, action={gate['failure_action']}")
        else:
            print(f"  [PASS] {gate['gate_id']}")

    return qc_report

def main():
    passing_metrics = {
        "identity_consistency": {"score": 0.95},
        "mask_edge_bleed": {"score": 0.95},
        "temporal_stability": {"score": 0.95},
        "loop_seam": {"score": 0.95},
        "audio_video": {"score": 0.95},
        "background_stability": {"score": 0.95},
        "identity_drift": {"score": 0.95}
    }

    # Scenario 1: Healthy
    run_smoke_scenario("healthy", passing_metrics)

    # Scenario 2: Motion Jitter (Repairable)
    motion_jitter_metrics = dict(passing_metrics)
    motion_jitter_metrics["temporal_stability"] = {"score": 0.5}
    report2 = run_smoke_scenario("motion-jitter", motion_jitter_metrics)
    assert report2["overall"]["recommended_action"] == "RETRY_STAGE"

    # Scenario 3: Costume Mismatch (Fatal)
    costume_fail_metrics = dict(passing_metrics)
    # costume_fidelity is handled specially via its own report file in this runner implementation
    report3 = run_smoke_scenario("costume-fail", costume_fail_metrics, costume_pass=False, require_costume=True)
    assert report3["overall"]["recommended_action"] == "ESCALATE_USER"

    # Scenario 4: Multiple failures (Priority Check)
    multi_fail_metrics = dict(passing_metrics)
    multi_fail_metrics["temporal_stability"] = {"score": 0.5}
    report4 = run_smoke_scenario("multi-fail", multi_fail_metrics, costume_pass=False, require_costume=True)
    assert report4["overall"]["recommended_action"] == "ESCALATE_USER"

    print("\n[SMOKE TEST PASSED] All stabilization scenarios validated.")

if __name__ == "__main__":
    main()
