#!/usr/bin/env python3
import json
import os
import pathlib
import shutil
import subprocess
import sys


def repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2]


def setup_mock_job(job_id: str):
    root = repo_root()
    jobs_dir = root / "sandbox" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    job_path = jobs_dir / f"{job_id}.job.json"
    job_data = {
        "job_id": job_id,
        "lane": "ai_video",
        "video": {"length_seconds": 4, "fps": 24},
        "shots": [
            {"shot_id": "shot_1", "visual": "scene 1", "t": [0, 2]},
            {"shot_id": "shot_2", "visual": "scene 2", "t": [2, 4]},
        ],
        "render": {
            "segment_generation_contract": "shot_by_shot",
            "background_asset": "sandbox/assets/demo/dance_loop.mp4",
        },
        "generation_policy": {"selected_video_provider": "vertex_veo"},
        "quality_policy": {"relpath": "repo/shared/qc_policy.v1.json"},
    }
    with open(job_path, "w") as f:
        json.dump(job_data, f, indent=2)

    return job_path


def seed_mock_quality_report(job_id: str, passing: bool):
    root = repo_root()
    qc_dir = root / "sandbox" / "logs" / job_id / "qc"
    qc_dir.mkdir(parents=True, exist_ok=True)

    # We create a recast quality report that explicitly passes or fails metrics
    # required by qc_policy.v1.json (e.g. background_stability)
    metric_score = {"score": 1.0 if passing else 0.0}
    perfect_score = {"score": 1.0}
    report = {
        "version": "recast_quality_report.v1",
        "job_id": job_id,
        "generated_at": "2026-01-01T00:00:00Z",
        "metrics": {
            "identity_consistency": perfect_score,
            "mask_edge_bleed": perfect_score,
            "temporal_stability": perfect_score,
            "loop_seam": perfect_score,
            "audio_video": perfect_score,
            "background_stability": metric_score,
            "identity_drift": metric_score,
            "composite_stability": metric_score,
            "shot_1_background_stability": perfect_score,
            "shot_1_identity_drift": perfect_score,
            "shot_2_background_stability": metric_score,
            "shot_2_identity_drift": metric_score,
        },
    }
    with open(qc_dir / "recast_quality_report.v1.json", "w") as f:
        json.dump(report, f, indent=2)


def run_orchestrator(job_id: str, inject_failure: bool = False):
    print(f"\n--- Running Orchestrator for {job_id} ---")
    root = repo_root()
    print("PYTHON EXECUTABLE:", sys.executable)

    seed_mock_quality_report(job_id, passing=not inject_failure)

    cmd = [
        "/opt/miniconda3/envs/cat-ai-factory/bin/python",
        "-m",
        "repo.services.orchestrator.ralph_loop",
        "--job",
        str(root / "sandbox" / "jobs" / f"{job_id}.job.json"),
        "--max-retries",
        "2",
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env["CAF_VEO_MOCK"] = "1"

    # We simulate a QC failure by tweaking the qc_runner via environment variable
    # If inject_failure is true, we force the mock runner to fail shot_2
    if inject_failure:
        env["CAF_MOCK_QC_FAIL_SHOT"] = "shot_2"

    try:
        subprocess.check_call(cmd, cwd=str(root), env=env)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"Orchestrator failed with code {e.returncode}")
        return e.returncode
    except Exception as e:
        print(f"Failed to execute orchestrator: {e}")
        return 1


def main():
    job_id = "smoke-test-reroll"
    root = repo_root()

    # Clean previous runs
    shutil.rmtree(root / "sandbox" / "output" / job_id, ignore_errors=True)
    shutil.rmtree(root / "sandbox" / "logs" / job_id, ignore_errors=True)

    setup_mock_job(job_id)

    print("Test 1: Normal targeted shot execution (mock QC pass)")
    run_orchestrator(job_id, inject_failure=False)

    state_file = root / "sandbox" / "logs" / job_id / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
            print(f"Final State: {state.get('state')}")
            assert state.get("state") == "COMPLETED"
    else:
        print("ERROR: state.json missing")
        sys.exit(1)

    print("\nTest 2: Forced Granular Retry (mock QC fail shot_2)")
    # Reset job output state
    shutil.rmtree(root / "sandbox" / "output" / job_id, ignore_errors=True)
    shutil.rmtree(root / "sandbox" / "logs" / job_id, ignore_errors=True)

    run_orchestrator(job_id, inject_failure=True)

    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
            print(f"Final State: {state.get('state')}")
            assert state.get("state") in ("FAIL_QUALITY", "COMPLETED")
    else:
        print("ERROR: state.json missing")
        sys.exit(1)

    worker_log_path = (
        root / "sandbox" / "logs" / job_id / "attempts" / "run-0002" / "worker.log"
    )
    if worker_log_path.exists():
        log_content = worker_log_path.read_text()
        if "shot_id='shot_2'" in log_content or "CAF_TARGET_SHOT_ID" in log_content:
            print("SUCCESS: Targeted re-roll detected in worker log!")
        else:
            print(
                "ERROR: Worker log for run-0002 did not indicate shot_2 was targeted."
            )
            sys.exit(1)
    else:
        print("ERROR: Retry attempt run-0002 was not executed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
